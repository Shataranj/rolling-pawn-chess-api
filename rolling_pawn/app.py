import logging
import os
import platform
from datetime import datetime
from functools import wraps
import io

import chess
import chess.engine
import chess.pgn
import jwt
from bson.objectid import ObjectId
from flask import Flask, request, jsonify
from flask_bcrypt import Bcrypt
from flask_cors import CORS, cross_origin
from flask_socketio import SocketIO

from database.db import initialize_db
from database.model import Game, User
# from validation_schema import userRegistrationSchema, gamePlaySchema
from socket_io_manager import SocketIOManager

app = Flask(__name__)
cors = CORS(app)
bcrypt = Bcrypt(app)
app.config['SECRET_KEY'] = "secret key"

app.config['MONGODB_SETTINGS'] = {
    'host': os.environ.get('MONGO_ATLAS') or 'mongodb://127.0.0.1:27017/rolling_pawn_api'
}

UI_ENDPOINT = os.environ.get('UI_ENDPOINT') or 'http://localhost:3000'

socketio = SocketIO(app, cors_allowed_origins=[
    '*'], logger=True, engineio_logger=True)

initialize_db(app)

platform_name = platform.platform()
platform_folder = 'linux' if platform_name.startswith('Linux') else 'mac'

engine = chess.engine.SimpleEngine.popen_uci(
    "rolling_pawn/stockfish/{0}/stockfish-11".format(platform_folder))
logging.basicConfig(level=logging.INFO)

socketio_manager = SocketIOManager(socketio)


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
            current_user = User.objects(
                username=data.get('username')).first()
        except:
            return jsonify({'message': 'Token is invalid'}), 403

        return f(current_user, *args, **kwargs)

    return decorated


def get_token(profile):
    return jwt.encode(
        {'username': profile.username, 'iat': datetime.utcnow()},
        app.config['SECRET_KEY'], algorithm='HS256').decode('utf-8')


@app.route('/users', methods=['POST'])
def register():
    body = request.get_json()
    try:
        # userRegistrationSchema.validate(body)
        username = body.get('username')
        user_email = body.get('email')
        firstname = body.get('firstname')
        lastname = body.get('lastname')
        gender = body.get('gender')
        password = body.get('password')

        user_password = bcrypt.generate_password_hash(
            password=password).decode('utf-8')

        users_registered = User.objects(username=username)
        if len(users_registered) == 0:
            User(username=username, email=user_email, password=user_password,
                 gender=gender, firstname=firstname, lastname=lastname).save()
            new_profile = User.objects(username=username)[0]
            return {
                'username': new_profile.username,
                'email': new_profile.email,
                'token': get_token(new_profile)
            }, 201
        else:
            return jsonify({'message': 'User already exists!'}), 409
    except Exception as e:
        return {'error': str(e)}, 400


@app.route('/sessions', methods=['POST'])
def login():
    body = request.get_json()
    username = body.get('username')
    password = body.get('password')
    profiles = User.objects(username=username)
    if profiles and bcrypt.check_password_hash(profiles[0].password, password):
        token = get_token(profiles[0])
        return {'token': token}, 200
    return {'message': 'Invalid username or password'}, 401


def get_winner(raw_result):
    if raw_result == '1/2-1/2':
        return 'NONE'
    if raw_result == '1-0':
        return 'WHITE'
    if raw_result == '0-1':
        return 'BLACK'


def process_result(raw_result, player_side):
    if raw_result == '*':
        return raw_result
    if raw_result == '1/2-1/2':
        return 'DRAW'

    winner = get_winner(raw_result)
    return 'WON' if winner == player_side.upper() else 'LOST'


def to_json(game, player_username):
    result = process_result(game.result, game.host_side)
    opponent = game.opponent
    side = game.host_side
    if game.opponent == player_username:
        side = 'WHITE' if game.host_side == 'BLACK' else 'BLACK'
        opponent = game.host_id
        result = process_result(game.result, side)

    return {
        'game_id': str(game.id),
        'result': result,
        'raw_result': game.result,
        'opponent': opponent,
        'side': side,
        'pgn': game.pgn,
        'status': game.status,
        'opponent_type': game.opponent_type,
        'created_at': str(game.created_at)
    }


def generate_pgn(board):
    return chess.Board().variation_san([move for move in board.move_stack])


@app.route('/my_games', methods=['GET'])
@cross_origin()
@token_required
def get_my_games(current_user):
    query = {'status': 'COMPLETED',
             '$or': [{'opponent': current_user.username},
                     {'host_id': current_user.username}]}

    games = Game.objects(__raw__=query)
    response = list()
    for game in games:
        game_json = to_json(game, current_user.username)
        response.append({k: game_json[k] for k in [
            'game_id', 'result', 'opponent', 'opponent_type', 'created_at']})

    return jsonify(response), 200


@app.route('/live_game', methods=['GET'])
@cross_origin()
@token_required
def get_live_game(current_user):
    query = {'status': 'IN_PROGRESS',
             '$or': [{'opponent': current_user.username},
                     {'host_id': current_user.username}]}

    game = Game.objects(__raw__=query).first()

    if game is None:
        return {'error': 'No live game'}, 404

    game_json = to_json(game, current_user.username)
    return {k: game_json[k] for k in [
        'game_id', 'opponent', 'opponent_type', 'pgn', 'side']}, 200


@app.route('/profile', methods=['GET'])
@cross_origin()
@token_required
def get_user_profile(current_user):
    return {k: current_user[k] for k in current_user if k not in ['password']}, 200


@app.route('/profile/stats', methods=['GET'])
@cross_origin()
@token_required
def get_user_stats(current_user):
    query = {'status': 'COMPLETED',
             '$or': [{'opponent': current_user.username},
                     {'host_id': current_user.username}]}

    games = Game.objects(__raw__=query)
    total_games = games.count()
    won_games = 0
    draw_games = 0
    for game in games:
        game_json = to_json(game, current_user.username)
        if game_json.get('result') == "WON":
            won_games += 1
        if game_json.get('result') == "DRAW":
            draw_games += 1

    return {
        "wins": won_games,
        "draws": draw_games,
        "lost": total_games - (won_games + draw_games),
        "total": total_games
    }


@app.route('/games', methods=['POST'])
@cross_origin()
@token_required
def add_board(current_user):
    body = request.get_json()

    player_side = body.get('color').upper()
    opponent_type = body.get('opponent_type').upper()
    opponent = body.get('opponent').lower()

    game_in_progress = Game.objects(
        host_id=current_user.username, status='IN_PROGRESS').first()

    if game_in_progress is not None:
        return {
            'error': 'A game is already in progress'
        }, 409

    game = Game(host_id=current_user.username, host_side=player_side,
                opponent_type=opponent_type, opponent=opponent)

    game.save()

    response = {
        'game_id': str(game.id),
        'status': game.status,
        'opponent_type': opponent_type,
        'side': player_side,
        'opponent': opponent
    }

    # Emit event to players for game_created
    socketio_manager.emit_to_user(current_user.username, 'game_created', response)
    socketio_manager.emit_to_user(opponent, 'game_created', response)
    
    if opponent_type == 'ENGINE' and player_side == 'BLACK':
        board = chess.Board()
        level = opponent.split('_')[-1]
        result = engine.play(board, chess.engine.Limit(depth=int(level)))
        board.push_uci(str(result.move))
        game.update(pgn=generate_pgn(board))

        # Emit this with some delay
        socketio_manager.emit_to_user(current_user.username, 'move', board.fen())

    return response, 201


def play_with_user(board, game, user_move, current_user):
    player_with_turn = game.opponent
    player_not_with_turn = game.host_id
    if (game.host_side == 'WHITE') == board.turn:
        player_with_turn = game.host_id
        player_not_with_turn = game.opponent

    if not player_with_turn == current_user.username:
        return {'error': 'Not your turn'}, 400

    board.push_uci(user_move)
    game.update(pgn=generate_pgn(board))
    socketio_manager.emit_to_user(player_not_with_turn, 'move', user_move)

    game_status = process_game_end(board, game)
    if game_status['game_ended']:
        # Emit these events with some delay
        socketio_manager.emit_to_user(game.opponent, 'game_ended', game_status)
        socketio_manager.emit_to_user(game.host_id, 'game_ended', game_status)

    return {'move': user_move, **game_status}, 200


# No need to emit the move using SocketIO because both players
# Will be playing from same App/Board


def play_with_guest(board, game, user_move):
    board.push_uci(user_move)
    game.update(pgn=generate_pgn(board))
    game_status = process_game_end(board, game)

    if game_status['game_ended']:
        # Emit this event with some delay
        socketio_manager.emit_to_user(game.host_id, 'game_ended', game_status)

    return {'move': user_move, **game_status}, 200


def play_with_engine(board, game, user_move):
    board.push_uci(user_move)
    game.update(pgn=generate_pgn(board))
    game_status = process_game_end(board, game)

    if game_status['game_ended']:
        return {'move': user_move, 'engine_move': None, **game_status}

    engine_level = int(game.opponent.split('_')[-1])
    result = engine.play(board, chess.engine.Limit(depth=engine_level))
    engine_move = str(result.move)
    board.push_uci(str(result.move))
    game.update(pgn=generate_pgn(board))

    # We need emit this with some delay
    socketio_manager.emit_to_user(game.host_id, 'move', engine_move)

    game_status = process_game_end(board, game)

    if game_status['game_ended']:
        # We need emit this with some delay
        socketio_manager.emit_to_user(game.host_id, 'game_ended', game_status)

    return {'move': user_move, 'engine_move': engine_move, **game_status}, 200

# TODO: Need to handle this properly. All the end cases are not covered


def process_game_end(board, game):
    if board.is_checkmate():
        game.update(result=board.result(), status='COMPLETED')
        winner = get_winner(board.result())
        return {'game_ended': True, 'winner': winner}
    else:
        return {'game_ended': False, 'winner': None}


@app.route('/play', methods=['POST'])
@cross_origin()
@token_required
def play_move(current_user):
    try:
        body = request.get_json()
        # gamePlaySchema.validate(body)
        game_id = body.get('game_id')
        user_move = "{0}{1}".format(body.get("from"), body.get("to"))

        query = {'_id': ObjectId(game_id),
                 '$or': [{'opponent': current_user.username},
                         {'host_id': current_user.username}]}
        game = Game.objects(__raw__=query).first()

        if game is None:
            return {'error': 'Invalid game Id'}, 400

        if game.status == 'COMPLETED':
            return {'error': 'Game is already finished'}, 400

        pgn = io.StringIO(game.pgn)
        game_from_pgn = chess.pgn.read_game(pgn)
        board = chess.Board()

        if game_from_pgn is not None:
            board = game_from_pgn.end().board()

        if not chess.Move.from_uci(user_move) in board.legal_moves:
            return {'error': 'Invalid move'}, 400

        # When playing with other user registered on platform
        if game.opponent_type == 'USER':
            return play_with_user(board.copy(), game, user_move, current_user)

        if game.opponent_type == 'GUEST':
            return play_with_guest(board.copy(), game, user_move)

        if game.opponent_type == 'ENGINE':
            return play_with_engine(board.copy(), game, user_move)

    except Exception as e:
        return {'error': str(e)}, 500


@app.route('/games/<game_id>', methods=['GET'])
@cross_origin()
@token_required
def get_game(current_user, game_id):
    query = {'_id': ObjectId(game_id),
             '$or': [{'opponent': current_user.username},
                     {'host_id': current_user.username}]}

    game = Game.objects(__raw__=query).first()

    if game is None:
        return {'error': 'Game not found'}, 404

    game_json = to_json(game, current_user.username)
    return {k: game_json[k] for k in [
        'game_id', 'opponent', 'opponent_type',
        'pgn', 'side', 'result', 'created_at']}, 200


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
        scores.append(
            {'move': move, 'score': info.get('score').white().score()})
    return {'scores': scores}, 200


port = int(os.environ.get("PORT", 5000))


@socketio.on('connect')
def on_new_connection():
    print("Client connected ---->" + (str(request.sid)))


@socketio.on('disconnect')
def on_disconnect():
    print("Client disconnected ---->" + (str(request.sid)))
    socketio_manager.remove_session(request.sid)


@socketio.on('new_user')
def on_new_user(user_id):
    print("User registered ---->" + user_id)
    socketio_manager.add_session(request.sid, user_id)


socketio.run(app, host='0.0.0.0', port=port, log_output=True)
