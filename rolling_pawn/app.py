import json
import os
import platform
import uuid
from datetime import datetime
from functools import wraps

import chess
import chess.engine
import chess.pgn
import jwt
from database.db import initialize_db
from database.model import GameBoardMapping, ChessGame, UserProfile
from flask import Flask, request, jsonify
from flask_bcrypt import Bcrypt
from flask_cors import CORS, cross_origin
from flask_socketio import SocketIO
from validation_schema import userRegistrationSchema, gamePlaySchema

app = Flask(__name__)
cors = CORS(app)
bcrypt = Bcrypt(app)
app.config['SECRET_KEY'] = "secret key"

app.config['MONGODB_SETTINGS'] = {
    'host': 'mongodb://127.0.0.1:27017/rolling_pawn_api'
}

UI_ENDPOINT = os.environ.get('UI_ENDPOINT') or 'http://localhost:3000'

socketio = SocketIO(app, cors_allowed_origins=[UI_ENDPOINT])

initialize_db(app)

platform_name = platform.platform()
platform_folder = 'linux' if platform_name.startswith('Linux') else 'mac'

engine = chess.engine.SimpleEngine.popen_uci("rolling_pawn/stockfish/{0}/stockfish-11".format(platform_folder))


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = ""
        if 'x-access-token' in request.headers:
            token = request.headers.get('x-access-token')
        if not token:
            return jsonify({'message': 'auth token is missing'}), 403
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'])
            current_user = UserProfile.objects(userId=data.get('user_id')).first()
        except:
            return jsonify({'message': 'Token is invalid'}), 403

        return f(current_user, *args, **kwargs)

    return decorated


def get_token(profile):
    return jwt.encode(
        {'user_id': profile.userId, 'user_email': profile.userEmail, 'board_id': profile.boardId,
         'iat': datetime.utcnow()},
        app.config['SECRET_KEY'], algorithm='HS256').decode('utf-8')


@app.route('/register', methods=['POST'])
def register():
    body = request.get_json()
    try:
        userRegistrationSchema.validate(body)
        board_id = body.get('board_id')
        user_id = body.get('user_id')
        user_email = body.get('user_email')
        user_password = bcrypt.generate_password_hash(password=body.get('user_password')).decode('utf-8')
        user_available = UserProfile.objects(userId=user_id)
        if len(user_available) == 0:
            UserProfile(userId=user_id, boardId=board_id, userEmail=user_email, userPassword=user_password).save()
            new_profile = UserProfile.objects(userId=user_id)[0]
            return {
                       'board_id': new_profile.boardId,
                       'user_id': new_profile.userId,
                       'user_email': new_profile.userEmail,
                       'token': get_token(new_profile)
                   }, 201
        else:
            return jsonify({'message': 'User ID is not available'}), 400
    except Exception as e:
        return {'error': str(e)}, 400


@app.route('/login', methods=['POST'])
def login():
    body = request.get_json()
    email = body.get('user_email')
    password = body.get('user_password')
    profiles = UserProfile.objects(userEmail=email)
    if profiles and bcrypt.check_password_hash(profiles[0].userPassword, password):
        token = get_token(profiles[0])
        return {'token': token}, 200
    return {'message': 'Invalid email or password'}, 401


@app.route('/my_games', methods=['GET'])
@cross_origin()
@token_required
def get_my_games(current_user):
    user_games_board_mapping = GameBoardMapping.objects(boardId=current_user.boardId)
    user_games = []

    for game_board_mapping in user_games_board_mapping:
        game = ChessGame.objects(gameId= game_board_mapping.gameId).first()
        user_games.append({
            "game_id": game_board_mapping.gameId,
            "with_engine": game_board_mapping.withEngine,
            "game_status": game_board_mapping.gameStatus,
            "created_at": game.createdAt,
            "player_1": current_user.userId,
            "player_2": "Engine"})

    response = {
        "games": user_games,
        "board_id": current_user.boardId
    }
    return jsonify(response), 200


@app.route('/profile', methods=['GET'])
@cross_origin()
@token_required
def get_user_profile(current_user):
    response = {
        "user_name": current_user.userId,
        "user_email": current_user.userEmail,
        "user_board_id": current_user.boardId
    }
    return jsonify(response), 200


@app.route('/create_game', methods=['POST'])
@cross_origin()
@token_required
def add_board(current_user):
    board = chess.Board()

    body = request.get_json()
    game_id = str(uuid.uuid1())
    board_id = body.get('board_id')
    player_side = body.get('color')
    with_engine = False
    # TODO: Set correct default value.
    engine_level = 1
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
@cross_origin()
@token_required
def play_with_ai(current_user):
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
@cross_origin()
@token_required
def move_to_ui(current_user):
    body = request.get_json()
    try:
        gamePlaySchema.validate(body)
        game_id = body.get("game_id")
        from_sq = body.get("from")
        to_sq = body.get("to")
        games = ChessGame.objects(gameId=game_id)
        if not games:
            return {'message': 'Invalid game Id'}, 400

        board = chess.Board()
        for move in games[0].moves:
            board.push_uci(move)

        response = {
            "from": from_sq,
            "to": to_sq,
            "game_id": game_id,
            "fen": board.fen()
        }

        if chess.Move.from_uci(from_sq + to_sq) in board.legal_moves:
            ChessGame.objects(gameId=game_id).update(push__moves=from_sq + to_sq)
            return response, 201

        socketio.emit("move", response, broadcast=True)
        return {'message': 'Invalid move'}, 400
    except Exception as e:
        return {'error': str(e)}, 400


@app.route('/get_all_games', methods=['GET'])
@cross_origin()
@token_required
def get_games(current_user):
    status = request.args.get('status')
    game_board = GameBoardMapping.objects(gameStatus=status) if status else GameBoardMapping.objects()
    result = []
    for game in game_board:
        result.append({
            "game_id": game.gameId,
            "board_id": game.boardId,
            "with_engine": game.withEngine,
            "game_status": game.gameStatus})

    return json.dumps(result), 200


@app.route('/game', methods=['GET'])
@cross_origin()
@token_required
def get_game(current_user):
    game_id = request.args.get('gameId')
    games = ChessGame.objects(gameId=game_id)
    if games:
        game = games[0]
        board = chess.Board()
        for move in game.moves:
            board.push_uci(move)
        return {"game_id": game.gameId,
                "fen": board.fen()}, 200
    return {'message': 'Invalid game Id'}, 400


@app.route('/pgn', methods=['GET'])
@cross_origin()
@token_required
def get_pgn(current_user):
    game_id = request.args.get('gameId')
    game_board = ChessGame.objects(gameId=game_id)
    if game_board:
        board = chess.Board()
        pgn = board.variation_san([chess.Move.from_uci(m) for m in game_board[0].moves])
        return {'pgn': pgn}, 200
    return {'message': 'Invalid game Id'}, 400


@app.route('/score', methods=['GET'])
@cross_origin()
@token_required
def get_score(current_user):
    game_id = request.args.get('gameId')
    depth = request.args.get('depth')
    games = ChessGame.objects(gameId=game_id)
    board = chess.Board()
    if not games:
        return {'message': 'Invalid game Id'}, 400
    scores = []
    for move in games[0].moves:
        board.push_uci(move)
        info = engine.analyse(board, chess.engine.Limit(depth=depth))
        scores.append({'move': move, 'score': info.get('score').white().score()})
    return {'scores': scores}, 200


port = int(os.environ.get("PORT", 5000))
socketio.run(app, host='0.0.0.0', port=port)
