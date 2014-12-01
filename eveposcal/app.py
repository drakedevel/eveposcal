from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy

app = Flask(__name__.split('.')[0], template_folder='../templates')
db = SQLAlchemy(app)
