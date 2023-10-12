import ast
import boto3
import re
import time

import server.server_plugins.resource_base as resource_base
from server.common import constants
from server.common import fm_logger
from server.dbmodule.objects import environment as env_db
from server.dbmodule.objects import resource as res_db
from server.server_plugins.aws import aws_helper

fmlogger = fm_logger.Logging()

DEFAULT_RDS_ENGINE = 'mysql'
DEFAULT_RDS_INSTANCE_CLASS = 'db.t1.micro'


class RDSResourceHandler(resource_base.ResourceBase):
    """RDS Resource handler."""

    awshelper = aws_helper.AWSHelper()

    allowed_commands = ["aws rds describe-db-parameters*",
                        "aws rds describe-db-security-groups*",
                        "aws rds describe-db-subnet-groups*",
                        "aws rds describe-engine-default-parameters*",
                        "aws rds describe-events*",
                        "aws rds describe-db-instances*"]

    help_commands = ["aws rds describe-db-parameters",
                     "aws rds describe-db-security-groups",
                     "aws rds describe-db-subnet-groups",
                     "aws rds describe-engine-default-parameters",
                     "aws rds describe-events",
                     "aws rds describe-db-instances"]

    def __init__(self):
        self.client = boto3.client('rds')

    def _verify(self, command):
        matched = None
        for pattern in RDSResourceHandler.allowed_commands:
            p = re.compile(pattern, re.IGNORECASE)
            matched = p.match(command)
            if matched:
                return True
        return False

    def create(self, env_id, resource_details):
        env_obj = env_db.Environment().get(env_id)
        res_type = resource_details['type']

        env_output_config = ast.literal_eval(env_obj.output_config)
        env_version_stamp = env_output_config['env_version_stamp']

        instance_id = env_obj.name + "-" + env_version_stamp
        db_name = constants.DEFAULT_DB_NAME

        vpc_id = ''
        vpc_traffic_block = []
        if 'vpc_id' in env_output_config and 'cidr_block' in env_output_config:
            vpc_id = env_output_config['vpc_id']
            vpc_traffic_block.append(env_output_config['cidr_block'])
        else:
            vpc_details = RDSResourceHandler.awshelper.get_vpc_details()
            vpc_id = vpc_details['vpc_id']
            vpc_traffic_block.append(vpc_details['cidr_block'])

        sec_group_name = instance_id + "-sql"
        sec_group_id = ''
        try:
            sec_group_id = RDSResourceHandler.awshelper.create_security_group_for_vpc(vpc_id, sec_group_name)
        except Exception as e:
            status = str(e)
            return status

        port_list = [3306]

        engine = DEFAULT_RDS_ENGINE
        instance_class = DEFAULT_RDS_INSTANCE_CLASS

        if 'configuration' in resource_details:
            if 'engine' in resource_details['configuration']:
                engine = resource_details['configuration']['engine']
            if 'flavor' in resource_details['configuration']:
                instance_class = resource_details['configuration']['flavor']

        publicly_accessible = False
        if 'policy' in resource_details:
            if resource_details['policy']['access'] == 'open':
                publicly_accessible = True
                vpc_traffic_block.append('0.0.0.0/0')

        try:
            RDSResourceHandler.awshelper.setup_security_group(vpc_id, vpc_traffic_block,
                                                              sec_group_id, sec_group_name, port_list)
        except Exception as e:
            status = str(e)
            try:
                RDSResourceHandler.awshelper.delete_security_group_for_vpc(vpc_id,
                                                                           sec_group_id,
                                                                           sec_group_name)
            except Exception as e1:
                fmlogger.error(e1)
                status = status + " + " + str(e1)
            return status
        
        try:
            self.client.create_db_instance(DBName=db_name,
                                           DBInstanceIdentifier=instance_id,
                                           DBInstanceClass=instance_class,
                                           Engine=engine,
                                           MasterUsername=constants.DEFAULT_DB_USER,
                                           MasterUserPassword=constants.DEFAULT_DB_PASSWORD,
                                           PubliclyAccessible=publicly_accessible,
                                           AllocatedStorage=5,
                                           VpcSecurityGroupIds=[sec_group_id],
                                           Tags=[{"Key": "Tag1", "Value": "Value1"}])
        except Exception as e:
            fmlogger.error("Exception encountered in creating rds instance %s" % e)
            status = str(e)
            try:
                RDSResourceHandler.awshelper.delete_security_group_for_vpc(vpc_id,
                                                                           sec_group_id,
                                                                           sec_group_name)
            except Exception as e1:
                fmlogger.error(e1)
                status = status + " + " + str(e1)
            return status

        status = constants.CREATION_REQUEST_RECEIVED
        count = 1

        instance_description = ''
        filtered_description = dict()

        res_data = {}
        res_data['env_id'] = env_id
        res_data['cloud_resource_id'] = instance_id
        res_data['type'] = res_type
        res_data['status'] = status
        res_id = res_db.Resource().insert(res_data)

        while status.lower() is not 'available':
            try:
                instance_description = self.client.describe_db_instances(DBInstanceIdentifier=instance_id)
                status = instance_description['DBInstances'][0]['DBInstanceStatus']
                if status.lower() == 'available':
                    break
                res_data['status'] = status
                res_data['filtered_description'] = str(filtered_description)
                res_data['detailed_description'] = str(instance_description)
                res_db.Resource().update(res_id, res_data)

                count = count + 1
                time.sleep(2)
            except Exception as e:
                fmlogger.error("Exception encountered in describing rds instance %s" % e)

        if status.lower() == 'available':
            # Saving vpc_id here for convenience as when we delete RDS instance we can directly read it
            # from the resource table than querying the env table.
            filtered_description['vpc_id'] = vpc_id
            filtered_description['sql-security-group-name'] = sec_group_name
            filtered_description['sql-security-group-id'] = sec_group_id
            filtered_description['DBInstanceIdentifier'] = instance_id
            filtered_description['DBInstanceClass'] = DEFAULT_RDS_INSTANCE_CLASS
            filtered_description['Engine'] = DEFAULT_RDS_ENGINE
            filtered_description['MasterUsername'] = constants.DEFAULT_DB_USER
            filtered_description['MasterUserPassword'] = constants.DEFAULT_DB_PASSWORD
            filtered_description['DBName'] = constants.DEFAULT_DB_NAME
            endpoint_address = instance_description['DBInstances'][0]['Endpoint']['Address']
            filtered_description['Address'] = endpoint_address
        else:
            status = 'create-failure: ' + status

        res_data['status'] = status
        res_data['filtered_description'] = str(filtered_description)
        res_data['detailed_description'] = str(instance_description)
        res_db.Resource().update(res_id, res_data)

        return status.lower()

    def delete(self, request_obj):
        instance_id = request_obj.cloud_resource_id

        try:
            self.client.delete_db_instance(DBInstanceIdentifier=instance_id,
                                           SkipFinalSnapshot=True)
        except Exception as e:
            fmlogger.error(e)
            res_db.Resource().delete(request_obj.id)

        db_obj = res_db.Resource().get_by_cloud_resource_id(instance_id)
        deleted = False
        count = 1
        while not deleted:
            try:
                status_dict = self.client.describe_db_instances(DBInstanceIdentifier=instance_id)
                status = status_dict['DBInstances'][0]['DBInstanceStatus']
                res_db.Resource().update(db_obj.id, {'status': status})
                count = count + 1
                time.sleep(2)
            except Exception as e:
                fmlogger.error(e)
                deleted = True

        try:
            filtered_description = ast.literal_eval(db_obj.filtered_description)
            sec_group_name = filtered_description['sql-security-group-name']
            sec_group_id = filtered_description['sql-security-group-id']
            vpc_id = filtered_description['vpc_id']
            try:
                RDSResourceHandler.awshelper.delete_security_group_for_vpc(vpc_id,
                                                                           sec_group_id,
                                                                           sec_group_name)
            except Exception as e:
                fmlogger.error(e)
        except Exception as e:
            fmlogger.error(e)

        res_db.Resource().delete(request_obj.id)

    def run_command(self, env_id, env_name, resource_obj, command):
        fmlogger.debug("Running command against RDS instance")

        if command.lower() == 'help':
            return RDSResourceHandler.help_commands

        command_output = ''

        is_supported_command = self._verify(command)
        if not is_supported_command:
            command_output = ["Command not supported"]
            return command_output

        command_output = RDSResourceHandler.awshelper.run_command(env_id, env_name,
                                                                  resource_obj, command)

        output_lines = command_output.split("\n")

        return output_lines
