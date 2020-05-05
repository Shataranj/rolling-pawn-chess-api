import os
import platform
from flask import Flask, request, Response
from database.db import initialize_db
from database.model import GameBoardMapping, ChessGame
import json
import uuid
import chess.engine
import chess
from flask_socketio import SocketIO, emit, send
from flask_cors import CORS, cross_origin

app = Flask(__name__)

app.config['MONGODB_SETTINGS'] = {
    'host': 'mongodb+srv://rolling:pawns@chess-cluster-h3zto.mongodb.net/rolling_pawn_api'
}

UI_ENDPOINT = os.environ.get('UI_ENDPOINT') or 'http://0.0.0.0:3000'

socketio = SocketIO(app, cors_allowed_origins=UI_ENDPOINT)

initialize_db(app)

platform_name = platform.platform()
platform_folder = 'linux' if platform_name.startswith('Linux') else 'mac'

engine = chess.engine.SimpleEngine.popen_uci("rolling_pawn/stockfish/{0}/stockfish-11".format(platform_folder))


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

    game_board =  GameBoardMapping(gameId=game_id, boardId=board_id, withEngine=with_engine).save()
    game_id = game_board.gameId
    status = game_board.gameStatus
    game_started_with = "Game started with Stockfish Engine" if with_engine else "Game started with other player"
    current_turn = "white" if board.turn else "black"
    if player_side == "black":
        result = engine.play(board, chess.engine.Limit(depth=engine_level))
        board.push_uci(str(result.move))
        initial_move["engine_move"] ={
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

    if  board.is_checkmate():
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
def test_socket():
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

port = int(os.environ.get("PORT", 5000))
socketio.run(app, host='0.0.0.0', port=port)
