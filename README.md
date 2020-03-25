# A RESTFUL API TO PLAY CHESS WITH **Stockfish** ENGINE


Rolling pawn api is a REST api built with Python and MongoDB, which uses **Stockfish - 11** engine. Currently it supports two endpoints which will be described below, but with all the capabilities Stockfish supports it can be used for features like:

* Opening Trainer
* Chess Game Analysis
* Annotating Games
* *and many more..*

## API DOCUMENTATION

### START A GAME

You can start game with the engine using the below endpoint. The payload also contains a boolean ```with_engine```, because in future we also have a plan to extend to toggle between **human and engine**.

**Endpoint:** ``` https://localhost:5000/create_game  ```

**Method:** ``` POST ```

**Header:** ``` Content-Type: application/json ```

**Payload:** 

```
{
    "board_id": "rolling-chess-board-21", 
    "with_engine": true, 
    "color": "white", 
    "engine_level": 1
}

```

**Schema Explanation:**

```
{
    "board_id": Unique ID of the client making call
    "with_engine": true/false, 
    "color": "white"/"black - To choose a side 
    "engine_level": Engine level (from 1 to 15)
}
```

**Response:**

```
{
    "board_id": "rolling-chess-board-21",
    "engine_level": 1,
    "game_id": "65e9f862-6e0f-11ea-ae3f-fad5b90f71a6",
    "game_with": "Game started with Stockfish Engine",
    "initial_move": {},
    "player_side": "white",
    "status": "In Progress"
}

```
The ``` initial_move ``` will have some value if player chooses "black". For example, for a payload like:

```
{
    "board_id": "rolling-chess-board-21", 
    "with_engine": true, 
    "color": "black", 
    "engine_level": 1
}

```

The response will be:

```
{
    "board_id": "rolling-chess-board-21",
    "engine_level": 1,
    "game_id": "04284816-6e66-11ea-8f9c-d2af391bd46a",
    "game_with": "Game started with Stockfish Engine",
    "initial_move": {
        "engine_move": {
            "from": "e2",
            "to": "e3"
        }
    },
    "player_side": "black",
    "status": "In Progress"
}

```

### PLAY GAME

You can continuing playing a game by providing the game ID with AI, untill there is a checkmate, which will be indicated by ``` game_over ``` attribute.

**Endpoint:** ``` https://localhost:5000/play  ```

**Method:** ``` POST ```

**Header:** ``` Content-Type: application/json ```

**Payload:** 

```
{
    "game_id": "65e9f862-6e0f-11ea-ae3f-fad5b90f71a6", 
    "from": "d2", 
    "to":"d4"
}

```

## APPLICATION DEPLOYED ON HEROKU

The application is deployed on Heroku. Please use the below URL to try it out:

**Server URL:** ``` https://rolling-pawn-chess.herokuapp.com/ ```

## DEPLOYING LOCALLY

Note: You need to have python-3.x.x installed on your machine.

**Step 1:**  Create a virtual environment. 

``` python -m venv <env-name> ```

**Step 2:**  Activate the virtual environment.

``` source <env-name>/bin/activate ```

**Step 3:**  Install dependencies

``` pip install -r requirements.txt ```

**Step 4:**  Start the server

``` python rolling_pawn/app.py ```

This should start your app at: ``` http://localhost:5000 ```