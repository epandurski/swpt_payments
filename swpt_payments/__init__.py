__version__ = '0.1.0'

import os
import os.path
import logging
import logging.config
from flask_env import MetaFlaskEnv

# Configure app logging. If the value of "$APP_LOGGING_CONFIG_FILE" is
# a relative path, the directory of this (__init__.py) file will be
# used as a current directory.
config_filename = os.environ.get('APP_LOGGING_CONFIG_FILE')
if config_filename:  # pragma: no cover
    if not os.path.isabs(config_filename):
        current_dir = os.path.dirname(__file__)
        config_filename = os.path.join(current_dir, config_filename)
    logging.config.fileConfig(config_filename, disable_existing_loggers=False)
else:
    logging.basicConfig(level=logging.WARNING)


def _get_default_base_url():
    port = os.environ.get('PORT', '8000')
    return f'http://localhost:{port}/'


class Configuration(metaclass=MetaFlaskEnv):
    SECRET_KEY = 'dummy-secret'
    SQLALCHEMY_DATABASE_URI = ''
    SQLALCHEMY_POOL_SIZE = None
    SQLALCHEMY_POOL_TIMEOUT = None
    SQLALCHEMY_POOL_RECYCLE = None
    SQLALCHEMY_MAX_OVERFLOW = None
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    DRAMATIQ_BROKER_CLASS = 'RabbitmqBroker'
    DRAMATIQ_BROKER_URL = 'amqp://guest:guest@localhost:5672'
    BASE_URL = _get_default_base_url()


def create_app(config_dict={}):
    from flask import Flask
    from .extensions import db, migrate, broker
    from .routes import web_api
    from .cli import swpt_payments
    from . import models  # noqa

    app = Flask(__name__)
    app.config.from_object(Configuration)
    app.config.from_mapping(config_dict)
    db.init_app(app)
    migrate.init_app(app, db)
    broker.init_app(app)
    app.register_blueprint(web_api, url_prefix='/')
    app.cli.add_command(swpt_payments)
    return app
