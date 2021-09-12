import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

import random
import string
import logging
import asyncio
from pathlib import Path
import json

SERVER_GAME_VERSION = "v1.9"

MAP_SEED = 42069
MAP_SIZE = {"x": 200, "y": 300} # *32 (tilesize)
MAP_GENERATOR_SETTINGS = {
	"start_height": 12,
	"map_octaves": 7,
	"map_period": 7,
	"map_lacunarity": 0.85,
	"ore_octaves": 4.42,
	"ore_period": 1.85,
	"ore_lacunarity": 0.5,
	"ore_persistency": 0.45
}
MAP_POI = {
    "shop": {"x": MAP_SIZE["x"] / 2 + 8, "y": 0},
    "refinery": {"x": MAP_SIZE["x"] / 2 + 16, "y": 0},
    "rocket": {"x": MAP_SIZE["x"] / 2 + 24, "y": 0}
}

PLAYER_SPAWNPOINT = {"x": 3200, "y": 300}

# Saved to FS
MAP_TILES = []
MAP_DROPPED_ITEMS = {}
MAP_PLACED_ITEMS = []
MAP_CURRENT_TIME = 0
PLAYER_DATA = {}

app = FastAPI()
logger = logging.getLogger("uvicorn.info")

def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choices(chars, k=size))

@app.on_event("startup")
async def startup_event():
    logger.info("Server starting...")

    load_fs_data()

    loop = asyncio.get_running_loop()
    # loop = asyncio.get_event_loop()
    loop.create_task(core_loop())

@app.on_event("shutdown")
def shutdown_event():
    save_fs_data()
    logger.info("Server stopped!")

async def core_loop():
    global MAP_CURRENT_TIME

    while True:
        sleep_time = 5.0
        # target_fps = 60.0

        await asyncio.sleep(sleep_time)

        # delta = 1.0 / target_fps
        MAP_CURRENT_TIME += sleep_time / 2

        await manager.broadcast(message={"event": "server", "type": "synctime", "clientid": 0, "data": {"time": MAP_CURRENT_TIME}})

class ConnectionManager:
    def __init__(self):
        self.clients = {}

    def connect(self, client_id, os_uid, username, websocket: WebSocket):
        global PLAYER_DATA

        self.clients[client_id] = {
            "os_uid": os_uid,
            "username": username,
            "position": {"x": 0, "y": 0},
            "websocket": websocket

        }

        if not os_uid in PLAYER_DATA:
            PLAYER_DATA[os_uid] = {
                "position": {
                    "x": PLAYER_SPAWNPOINT["x"],
                    "y": PLAYER_SPAWNPOINT["y"]
                },
                "inventory": {},
                "has_flashlight": False,
                "holding_item": "",
                "current_drill_level": 0,
                "money": 0
            }

    def disconnect(self, websocket: WebSocket):
        for client in self.clients.keys():
            if self.clients[client]["websocket"] == websocket:
                self.clients.pop(client)
                break
    
    def get_username(self, websocket: WebSocket):
        for client in self.clients.keys():
            if self.clients[client]["websocket"] == websocket:
                return self.clients[client]["username"]

    def get_client_id(self, websocket: WebSocket):
        for client in self.clients.keys():
            if self.clients[client]["websocket"] == websocket:
                return client

    async def broadcast(self, exclude_client_id = None, message = {}):
        for client in self.clients.keys():
            try:
                if client != exclude_client_id:
                    await self.clients[client]["websocket"].send_json(message, "binary")
            except:
                pass
    
    def get_clients(self):
        formatted_clients = {}
        for client in self.clients.keys():
            try:
                formatted_clients[client] = {
                    "username": self.clients[client]["username"],
                    "position": self.clients[client]["position"]
                }
            except:
                pass
            
        return formatted_clients
    
    def get_client_os_uid(self, client_id):
        return self.clients[client_id]["os_uid"]
    
    def update_player_position(self, client_id, position):
        if client_id in self.clients.keys():
            self.clients[client_id]["position"] = position
        PLAYER_DATA[self.get_client_os_uid(client_id)]["position"] = position
    
    def update_player_inventory(self, client_id, block_id, count):
        if not str(block_id) in PLAYER_DATA[self.get_client_os_uid(client_id)]["inventory"]:
            PLAYER_DATA[self.get_client_os_uid(client_id)]["inventory"][str(block_id)] = count
        else:
            PLAYER_DATA[self.get_client_os_uid(client_id)]["inventory"][str(block_id)] += count
    
    def update_player_data(self, client_id, has_flashlight, holding_item, current_drill_level, money):
        PLAYER_DATA[self.get_client_os_uid(client_id)]["has_flashlight"] = has_flashlight
        PLAYER_DATA[self.get_client_os_uid(client_id)]["holding_item"] = holding_item
        PLAYER_DATA[self.get_client_os_uid(client_id)]["current_drill_level"] = current_drill_level
        PLAYER_DATA[self.get_client_os_uid(client_id)]["money"] = money


manager = ConnectionManager()

@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            data = {}
            try:
                data = await websocket.receive_json("binary")
            except KeyError:
                data = await websocket.receive_json("text")
            
            event = data["event"] if "event" in data else ""
            type = data["type"] if "type" in data else ""
            client_id = data["client_id"] if "client_id" in data else ""
            username = data["username"] if "username" in data else ""
            # event_data = data["data"] if "data" in data else ""

            if event == "handshake":

                if type == "requestid":

                        client_id = id_generator(size=6)
                        await websocket.send_json({"event": "handshake", "type": "responseid", "data": client_id}, "binary")
                
                if type == "requestconnect":
                    status = "OK"

                    if data["game_version"] != SERVER_GAME_VERSION:
                        status = "UNSUPPORTED_GAME_VERSION"
                    else:
                        os_uid = data["os_uid"] if "os_uid" in data else client_id
                        manager.connect(client_id=client_id, os_uid=os_uid, username=username, websocket=websocket)
                        logger.info(username + " (" + client_id + ") has joined the server!")

                        await manager.broadcast(message={"event": "game", "type": "connected", "client_id": client_id, "username": username})

                    await websocket.send_json({"event": "handshake", "type": "responseconnect", "data": status}, "binary")
                    await websocket.send_json({"event": "server", "type": "synctime", "clientid": 0, "data": {"time": MAP_CURRENT_TIME}})

            if event == "game":
                    
                    if type == "requestmapdata":

                        response = {
                            "map_seed": MAP_SEED,
                            "map_size": MAP_SIZE,
                            "map_generator_settings": MAP_GENERATOR_SETTINGS,
                            "map_poi": MAP_POI
                        }
                        await websocket.send_json({"event": "game", "type": "responsemapdata", "data": response}, "binary")

                    if type == "requestmaptiles":

                        response_map_tiles = []

                        for tile_data in MAP_TILES:
                            response_map_tiles.append(tile_data)

                            if len(response_map_tiles) >= 100:
                                await websocket.send_json({"event": "game", "type": "responsemaptiles", "data": response_map_tiles}, "binary")
                                response_map_tiles = []

                        if len(response_map_tiles) > 0:
                            await websocket.send_json({"event": "game", "type": "responsemaptiles", "data": response_map_tiles}, "binary")
                    
                    if type == "requestmapdroppeditems":

                        response_map_dropped_items = []

                        for item_uid in MAP_DROPPED_ITEMS:
                            item_data = MAP_DROPPED_ITEMS[item_uid]
                            item_data["uid"] = item_uid

                            response_map_dropped_items.append(item_data)

                            if len(response_map_dropped_items) >= 100:
                                await websocket.send_json({"event": "game", "type": "responsemapdroppeditems", "data": response_map_dropped_items}, "binary")
                                response_map_dropped_items = []

                        if len(response_map_dropped_items) > 0:
                            await websocket.send_json({"event": "game", "type": "responsemapdroppeditems", "data": response_map_dropped_items}, "binary")
                    
                    if type == "requestclients":
                        response = manager.get_clients()

                        await websocket.send_json({"event": "game", "type": "responseclients", "data": response}, "binary")
                    
                    if type == "requestplayerspawnpoint":
                        # spawnpoint = PLAYER_SPAWNPOINT.copy()
                        # spawnpoint["x"] += random.randrange(-50, 300)
                        spawnpoint = PLAYER_DATA[manager.get_client_os_uid(client_id)]["position"]
                        await websocket.send_json({"event": "game", "type": "responseplayerspawnpoint", "data": spawnpoint}, "binary")
                    
                    if type == "requestplayerinventory":
                        inventory = PLAYER_DATA[manager.get_client_os_uid(client_id)]["inventory"]
                        await websocket.send_json({"event": "game", "type": "responseplayerinventory", "data": inventory}, "binary")
                    
                    if type == "requestplayerdata":
                        await websocket.send_json({"event": "game", "type": "responseplayerdata", "data": {
                            "has_flashlight": PLAYER_DATA[manager.get_client_os_uid(client_id)]["has_flashlight"],
		                    "holding_item": PLAYER_DATA[manager.get_client_os_uid(client_id)]["holding_item"],
		                    "current_drill_level": PLAYER_DATA[manager.get_client_os_uid(client_id)]["current_drill_level"],
		                    "money": PLAYER_DATA[manager.get_client_os_uid(client_id)]["money"]
                        }}, "binary")

                    if type == "playerposition":
                        position = data["data"]
                        manager.update_player_position(client_id, position)
                        await manager.broadcast(message={"event": "game", "type": "playerposition", "client_id": client_id, "data": position})
                    
                    if type == "playerhandrotation":
                        rotation = data["data"]
                        await manager.broadcast(message={"event": "game", "type": "playerhandrotation", "client_id": client_id, "data": rotation})
                    
                    if type == "updateplayerdata":
                        has_flashlight = data["data"]["has_flashlight"]
                        holding_item = data["data"]["holding_item"]
                        current_drill_level = data["data"]["current_drill_level"]
                        money = data["data"]["money"]

                        manager.update_player_data(client_id, has_flashlight, holding_item, current_drill_level, money)

                        await manager.broadcast(message={"event": "game", "type": "playerdataresponse", "client_id": client_id, "data": {
                            "has_flashlight": has_flashlight,
		                    "holding_item": holding_item,
		                    "current_drill_level": current_drill_level
                        }})
                    
                    if type == "settile":
                        tile_position = {"x": data["data"]["x"], "y": data["data"]["y"]}
                        tile_id = data["data"]["id"]

                        already_mined = False
                        save_tile = True
                        for tile in MAP_TILES:
                            if tile["x"] == tile_position["x"] and tile["y"] == tile_position["y"]:
                                if tile["id"] == tile_id:
                                    already_mined = True
                                else:
                                    save_tile = False
                                    tile["id"] = tile_id
                        
                        if save_tile and not already_mined:
                            MAP_TILES.append({"x": tile_position["x"], "y": tile_position["y"], "id": tile_id})

                        await manager.broadcast(message={"event": "game", "type": "settile", "client_id": client_id, "data": data["data"]})

                    if type == "dropitem":
                        tile_position = {"x": data["data"]["x"], "y": data["data"]["y"]}
                        tile_id = data["data"]["id"]
                        tile_drop_id = id_generator(size=6)

                        tile_drop = {
                            "x": tile_position["x"],
                            "y": tile_position["y"],
                            "id": tile_id,
                            "uid": tile_drop_id
                        }

                        MAP_DROPPED_ITEMS[tile_drop_id] = {
                            "x": tile_position["x"],
                            "y": tile_position["y"],
                            "id": tile_id
                        }

                        await manager.broadcast(message={"event": "game", "type": "dropitem", "client_id": client_id, "data": tile_drop})
                    
                    if type == "removedroppeditem":

                        if data["data"]["uid"] in MAP_DROPPED_ITEMS:
                            MAP_DROPPED_ITEMS.pop(data["data"]["uid"])
                        
                        # manager.update_player_inventory(client_id, data["data"]["block_id"], 1)

                        await manager.broadcast(message={"event": "game", "type": "removedroppeditem", "client_id": client_id, "data": data["data"]})
                    
                    if type == "addinventoryitem":

                        manager.update_player_inventory(client_id, data["data"]["block_id"], data["data"]["count"])
                    
                    if type == "requestmapplaceditems":
                        await manager.broadcast(message={"event": "game", "type": "responsemapplaceditems", "client_id": client_id, "data": MAP_PLACED_ITEMS})
                    
                    if type == "addmapplaceditem":

                        is_chest = data["data"]["type"] == "CHEST"

                        item_data = {
                            "x": data["data"]["x"],
                            "y": data["data"]["y"],
                            "type": data["data"]["type"]
                        }

                        if is_chest:
                            chest_id = id_generator(size=6)
                            item_data["chest_id"] = chest_id

                        MAP_PLACED_ITEMS.append(item_data)

                        await manager.broadcast(message={"event": "game", "type": "responsemapplaceditems", "client_id": client_id, "data": MAP_PLACED_ITEMS})

                    if type == "removemapplaceditem":

                        for placed_item in MAP_PLACED_ITEMS:
                            if placed_item["x"] == data["data"]["x"] and placed_item["y"] == data["data"]["y"]:
                                MAP_PLACED_ITEMS.remove(placed_item)
                                break
                        
                        await manager.broadcast(message={"event": "game", "type": "responsemapplaceditems", "client_id": client_id, "data": MAP_PLACED_ITEMS})
                    
                    if type == "addchestitem":
                        for item in MAP_PLACED_ITEMS:
                            if item["type"] == "CHEST":
                                if item["chest_id"] == data["data"]["chest_id"]:
                                    if not "chest_inventory" in item:
                                        item["chest_inventory"] = {}

                                    if not str(data["data"]["block_id"]) in item["chest_inventory"]:
                                        item["chest_inventory"][str(data["data"]["block_id"])] = data["data"]["count"]
                                    else:
                                        item["chest_inventory"][str(data["data"]["block_id"])] += data["data"]["count"]
                                    

                        CHEST_DATA = {
                            "chest_id": data["data"]["chest_id"],
                            "block_id": data["data"]["block_id"],
                            "count": data["data"]["count"]
                        }

                        await manager.broadcast(message={"event": "game", "type": "addchestitem", "client_id": client_id, "data": CHEST_DATA})

    except WebSocketDisconnect:
        logger.info(manager.get_username(websocket) + " (" + manager.get_client_id(websocket) + ") has left the server!")
        await manager.broadcast(message={"event": "game", "type": "disconnected", "client_id": manager.get_client_id(websocket), "username": manager.get_username(websocket)})
        manager.disconnect(websocket)

def load_fs_data():
    global MAP_TILES
    global MAP_DROPPED_ITEMS
    global MAP_PLACED_ITEMS
    global MAP_CURRENT_TIME
    global PLAYER_DATA

    global MAP_SEED
    global MAP_SIZE
    global MAP_GENERATOR_SETTINGS
    global MAP_POI
    global PLAYER_SPAWNPOINT

    Path("./gamedata").mkdir(parents=True, exist_ok=True)

    try:
        with open("./server.json", 'r') as reader:
            data = json.load(reader)
            MAP_SEED = data["map_seed"]
            MAP_SIZE = data["map_size"]
            MAP_GENERATOR_SETTINGS = data["map_generator_settings"]
            MAP_POI = data["map_poi"]
            PLAYER_SPAWNPOINT = data["player_spawn_point"]
    except:
        with open("./server.json", 'w') as outfile:
            data = {
                "map_seed": MAP_SEED,
                "map_size": MAP_SIZE,
                "map_generator_settings": MAP_GENERATOR_SETTINGS,
                "map_poi": MAP_POI,
                "player_spawn_point": PLAYER_SPAWNPOINT
            }
            json.dump(data, outfile)

    try:
        with open("./gamedata/map.json", 'r') as reader:
            data = json.load(reader)
            MAP_TILES = data["map_tiles"]
            MAP_DROPPED_ITEMS = data["map_dropped_items"]
            MAP_PLACED_ITEMS = data["map_placed_items"]
            MAP_CURRENT_TIME = data["map_time"]
    except:
        save_fs_data(save_map_data=True, save_player_data=False)

    try:
        with open("./gamedata/players.json", 'r') as reader:
            data = json.load(reader)
            PLAYER_DATA = data["player_data"]
    except:
        save_fs_data(save_map_data=False, save_player_data=True)

def save_fs_data(save_map_data: bool = True, save_player_data: bool = True):
    if save_map_data:
        with open("./gamedata/map.json", 'w') as outfile:
            data = {
                "map_tiles": MAP_TILES,
                "map_dropped_items": MAP_DROPPED_ITEMS,
                "map_placed_items": MAP_PLACED_ITEMS,
                "map_time": MAP_CURRENT_TIME
            }
            json.dump(data, outfile)
    
    if save_player_data:
        with open("./gamedata/players.json", 'w') as outfile:
            data = {
                "player_data": PLAYER_DATA
            }
            json.dump(data, outfile)
