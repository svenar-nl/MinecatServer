# MinecatServer
Server for the game Minecat


## Installation
run `python -m pip -r requirements.txt` to install the server dependencies


## Running
Run `uvicorn server:app` to start the server

The default server port is `8000`.

Run `uvicorn server:app --host 0.0.0.0 --port 8069` to run the Minecat server on a different port.


## Developing
Run `uvicorn server:app --reload` (or with your custom port) to run the Minecat server in development mode.

Every server file change the server automatically restarts to increase development speed.


## License
MIT