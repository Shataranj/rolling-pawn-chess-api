from .db import db
import datetime

class GameBoardMapping(db.Document):
    gameId = db.StringField(required=True)
    boardId = db.StringField(required=True)
    gameStatus = db.StringField(default="IN_PROGRESS", choices=('IN_PROGRESS', 'COMPLETED'))
    withEngine = db.BooleanField(default=True)
    side = db.StringField(default="white", choices=('white', 'black'))

class ChessGame(db.Document):
    gameId = db.StringField(required=True, primary_key=True)
    currentFen = db.StringField(required=True)
    moves = db.ListField(default=[])
    result = db.StringField(required=True, default="*", choices=('1-0','0-1','1/2-1/2','*'))
    withEngine = db.BooleanField()
    engineLevel = db.IntField(default=4)
    currentTurn = db.StringField(required=True, choices=('white', 'black'))
    createdAt = db.DateTimeField(default=datetime.datetime.utcnow)

class UserProfile(db.Document):
    boardId = db.StringField(required=True, max_length=80)
    userId = db.StringField(required=True, max_length=20, primary_key=True)
    userEmail = db.EmailField(max_length=80, required=True, unique=True)
    userPassword = db.StringField(max_length=80, required=True)
    isAdmin = db.BooleanField(default=False)
