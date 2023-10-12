import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError as IntegrityError

from server.common import fm_logger
from server.dbmodule import db_base

fmlogger = fm_logger.Logging()


class Resource(db_base.Base):
    __tablename__ = 'resource'
    __table_args__ = {'extend_existing': True}

    id = sa.Column(sa.Integer, primary_key=True)
    env_id = sa.Column(sa.Integer)
    cloud_resource_id = sa.Column(sa.Text, nullable=False)
    type = sa.Column(sa.String, nullable=False)
    status = sa.Column(sa.String)
    input_config = sa.Column(sa.Text)
    filtered_description = sa.Column(sa.Text)
    detailed_description = sa.Column(sa.Text)

    def __init__(self):
        pass

    @classmethod
    def to_json(self, res):
        res_json = {}
        #res_json['id'] = res.id
        res_json['env_id'] = res.env_id
        res_json['cloud_resource_id'] = res.cloud_resource_id
        res_json['type'] = res.type
        res_json['status'] = res.status
        res_json['input_config'] = str(res.input_config)
        res_json['filtered_description'] = str(res.filtered_description)
        res_json['detailed_description'] = str(res.detailed_description)
        return res_json

    def get(self, res_id):
        res = ''
        try:
            session = db_base.get_session()
            res = session.query(Resource).filter_by(id=res_id).first()
            session.close()
        except IntegrityError as e:
            fmlogger.debug(e)
        return res

    def get_by_cloud_resource_id(self, cloud_resource_id):
        res = ''
        try:
            session = db_base.get_session()
            res = session.query(Resource).filter_by(cloud_resource_id=cloud_resource_id).first()
            session.close()
        except IntegrityError as e:
            fmlogger.debug(e)
        return res

    def get_resource_for_env_by_type(self, env_id, res_type):
        res = ''
        try:
            session = db_base.get_session()
            res = session.query(Resource).filter_by(env_id=env_id).filter_by(type=res_type).first()
            session.close()
        except IntegrityError as e:
            fmlogger.debug(e)
        return res

    def get_resources_for_env(self, env_id):
        res = ''
        try:
            session = db_base.get_session()
            res = session.query(Resource).filter_by(env_id=env_id).all()
            session.close()
        except IntegrityError as e:
            fmlogger.debug(e)
        return res

    def get_all(self):
        res_list = ''
        try:
            session = db_base.get_session()
            res_list = session.query(Resource).all()
            session.close()
        except IntegrityError as e:
            fmlogger.debug(e)
        return res_list

    def insert(self, res_data):
        self.env_id = res_data['env_id']
        self.cloud_resource_id = res_data['cloud_resource_id']
        self.type = res_data['type']
        self.status = res_data['status']
        if 'input_config' in res_data: self.input_config = res_data['input_config']
        try:
            session = db_base.get_session()
            session.add(self)
            session.commit()
            session.close()
        except IntegrityError as e:
            fmlogger.debug(e)
        return self.id

    def update(self, res_id, res_data):
        try:
            session = db_base.get_session()
            res = session.query(Resource).filter_by(id=res_id).first()
            if 'status' in res_data: res.status = res_data['status']
            if 'input_config' in res_data: res.input_config = res_data['input_config']
            if 'filtered_description' in res_data: res.filtered_description = res_data['filtered_description']
            if 'detailed_description' in res_data: res.detailed_description = res_data['detailed_description']
            session.commit()
            session.close()
        except IntegrityError as e:
            fmlogger.debug(e)

    def delete(self, res_id):
        try:
            session = db_base.get_session()
            res = session.query(Resource).filter_by(id=res_id).first()
            session.delete(res)
            session.commit()
            session.close()
        except IntegrityError as e:
            fmlogger.debug(e)

    def update_res_for_env(self, env_id, res_data):
        res = ''
        try:
            session = db_base.get_session()
            res = session.query(Resource).filter_by(env_id=env_id).first()
            if 'status' in res_data: res.status = res_data['status']
            session.commit()
            session.close()
        except IntegrityError as e:
            fmlogger.debug(e)
        return res.id

    def get_by_env(self, env_id):
        res_list = ''
        try:
            session = db_base.get_session()
            res_list = session.query(Resource).filter_by(env_id=env_id).all()
            session.close()
        except IntegrityError as e:
            fmlogger.debug(e)
        return res_list
