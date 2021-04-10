from .db import db
import datetime
class Game(db.Document):
    moves = db.ListField(default=[])
    result = db.StringField(required=True, default="*", choices=('1-0','0-1','1/2-1/2','*'))
    status = db.StringField(required=True, default="IN_PROGRESS", choices=('IN_PROGRESS','COMPLETED'))
    host_id = db.StringField(required=True, max_length=20)
    host_side = db.StringField(required=True, default="WHITE", choices=('WHITE', 'BLACK'))
    opponent_type = db.StringField(required=True, default="ENGINE", choices=('ENGINE', 'USER', 'GUEST'))
    opponent = db.StringField(required=True, max_length=80)
    created_at = db.DateTimeField(default=datetime.datetime.utcnow)

class User(db.Document):
    username = db.StringField(required=True, max_length=20, primary_key=True)
    email = db.EmailField(max_length=80, required=True, unique=True)
    password = db.StringField(max_length=80, required=True)
    firstname = db.StringField(max_length=80, required=True)
    lastname = db.StringField(max_length=80, required=True)
    created_at = db.DateTimeField(default=datetime.datetime.utcnow)
    gender = db.StringField(required=True, choices=('M','F','O','U'))
