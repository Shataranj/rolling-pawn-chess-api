import os
import platform
from flask import Flask, request, Response
from database.db import initialize_db
from database.model import GameBoardMapping, ChessGame, UserProfile
from validation_schema import userRegistrationSchema
import jwt
import json
import uuid
import chess.engine
from flask_bcrypt import Bcrypt
import chess
import chess.pgn
from flask_socketio import SocketIO, emit, send
from flask_cors import CORS, cross_origin

app = Flask(__name__)
cors = CORS(app)
bcrypt = Bcrypt(app)
SECRET_KEY = "secret key"

app.config['MONGODB_SETTINGS'] = {
    'host': 'mongodb+srv://rolling:pawns@chess-cluster-h3zto.mongodb.net/rolling_pawn_api'
}

UI_ENDPOINT = os.environ.get('UI_ENDPOINT') or 'http://0.0.0.0:3000'

socketio = SocketIO(app, cors_allowed_origins=UI_ENDPOINT)

initialize_db(app)

platform_name = platform.platform()
platform_folder = 'linux' if platform_name.startswith('Linux') else 'mac'

engine = chess.engine.SimpleEngine.popen_uci("rolling_pawn/stockfish/{0}/stockfish-11".format(platform_folder))


@app.route('/register', methods=['POST'])
def register():
    body = request.get_json()
    try:
        userRegistrationSchema.validate(body)
        board_id = body.get('board_id')
        user_id = body.get('user_id')
        user_email = body.get('user_email')
        user_password = bcrypt.generate_password_hash(password=body.get('user_password')).decode('utf-8')
        UserProfile(userId=user_id, boardId=board_id, userEmail=user_email, userPassword=user_password).save()
        return {
                   'board_id': board_id,
                   'user_id': user_id,
                   'user_email': user_email
               }, 201
    except Exception as e:
        return {'error': str(e)}, 400


@app.route('/login', methods=['POST'])
def login():
    body = request.get_json()
    email = body.get('user_email')
    password = body.get('user_password')
    profiles = UserProfile.objects(userEmail=email)
    if profiles and bcrypt.check_password_hash(profiles[0].userPassword, password):
        profile = profiles[0]
        token = jwt.encode({'userEmail': profile.userEmail, 'boardId': profile.boardId}, SECRET_KEY,
                           algorithm='HS256').decode('utf-8')
        return json.dumps({'token': token}), 200
    return {'message': 'Invalid email or password'}, 401


@app.route('/create_game', methods=['POST'])
def add_board():
    board = chess.Board()

    body = request.get_json()
    game_id = str(uuid.uuid1())
    board_id = body.get('board_id')
    player_side = body.get('color')
    with_engine = False
    initial_move = {}

    if body.get('with_engine'):
        with_engine = True
        engine_level = body.get('engine_level')
        if player_side is 'black':
            result = engine.play(board, chess.engine.Limit(depth=engine_level))
            board.push_uci(str(result.move))

    game_board = GameBoardMapping(gameId=game_id, boardId=board_id, withEngine=with_engine).save()
    game_id = game_board.gameId
    status = game_board.gameStatus
    game_started_with = "Game started with Stockfish Engine" if with_engine else "Game started with other player"
    current_turn = "white" if board.turn else "black"
    if player_side == "black":
        result = engine.play(board, chess.engine.Limit(depth=engine_level))
        board.push_uci(str(result.move))
        initial_move["engine_move"] = {
            "from": str(result.move)[:2],
            "to": str(result.move)[2:4]
        }

    ChessGame(gameId=game_id, currentFen=str(board.fen()), engineLevel=engine_level, currentTurn=current_turn).save()

    return {
               'game_id': game_id,
               'board_id': board_id,
               'status': status,
               'game_with': game_started_with,
               'player_side': player_side,
               'engine_level': engine_level,
               'initial_move': initial_move
           }, 201


@app.route('/play', methods=['POST'])
def play_with_ai():
    body = request.get_json()
    game_id = body.get('game_id')
    user_move = "{0}{1}".format(body.get("from"), body.get("to"))
    game_over = False

    game_obj = ChessGame.objects(gameId=game_id).first()
    engine_level = game_obj.engineLevel
    current_fen = game_obj.currentFen
    board = chess.Board(current_fen)
    board.push_uci(user_move)

    if not board.is_checkmate():
        result = engine.play(board, chess.engine.Limit(depth=engine_level))
        board.push_uci(str(result.move))
    else:
        game_over = True
        ChessGame.objects(gameId=game_id).update(set__result=board.result())
        GameBoardMapping.objects(gameId=game_id).update(set__gameStatus="Completed")

    if board.is_checkmate():
        game_over = True
        ChessGame.objects(gameId=game_id).update(set__result=board.result())
        GameBoardMapping.objects(gameId=game_id).update(set__gameStatus="Completed")

    current_turn = "white" if board.turn else "black"
    ChessGame.objects(gameId=game_id).update(set__currentFen=str(board.fen()))
    ChessGame.objects(gameId=game_id).update(set__currentTurn=current_turn)

    response = {
        "engine_move":
            {
                "from": str(result.move)[:2],
                "to": str(result.move)[2:4]
            },
        "fen": board.fen(),
        "game_over": game_over
    }
    return response, 201


@app.route('/move', methods=['POST'])
def move_to_ui():
    body = request.get_json()
    game_id = body.get("game_id")
    from_sq = body.get("from")
    to_sq = body.get("to")

    response = {
        "from": from_sq,
        "to": to_sq,
        "game_id": game_id
    }
    socketio.emit("move", response, broadcast=True)
    return response, 201


@app.route('/get_all_games', methods=['GET'])
@cross_origin()
def get_games():
    status = request.args.get('status')
    print (status)
    game_board = GameBoardMapping.objects(gameStatus=status) if status else GameBoardMapping.objects()
    result = []
    # response = {}
    for game in game_board:
        result.append({
            "game_id": game.gameId,
            "board_id": game.boardId,
            "with_engine": game.withEngine,
            "game_status": game.gameStatus})

    # response = {
    #     "total": len(result),
    #     "games": result
    # }
    return json.dumps(result), 200


port = int(os.environ.get("PORT", 5000))
socketio.run(app, host='0.0.0.0', port=port)
