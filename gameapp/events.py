from flask import request
from flask_socketio import SocketIO, join_room
from .classes import Player, Room
from flask_security import current_user
from gameapp import db, io

prefix = "[io-Server]: "

rooms = {}

# This is the server-sided code for socket.io (server is 'io', client is 'socket')
# The following lines are the events that will be catched and answerd by the server

# CONNECTION
# --------------------------------------------------------------------------------------------
@io.on("connect_me")
# ^ request for connection to given room by the client
def connect_client_to_room(data):
  room = data["room"]
  if room in rooms.keys():
    roomObj = rooms[room]
    # ^ if the Lobby exists ...
    print( prefix + "User: '"+request.sid + "' wants to connect to Room: '"+room+"'" )
    if roomObj.playerX is not None and roomObj.playerO is not None:
      #Lobby is full, inform client
      io.emit("lobby_full", to=request.sid)
      print( prefix + "Connection not possible, room already full")
    else:
      #Add Client to room
      addAndConnectPlayer(data)
  else: 
    rooms[room] = Room()
    # ^ create a new room
    print(prefix+"Creating new room")
    addAndConnectPlayer(data)
    # ^ add Client to it
    

def addAndConnectPlayer(data):
  # Handles connection of a Client
  room = data["room"]
  roomObj = rooms[data["room"]]
  opponent = None
  if roomObj.playerX == None:
    roomObj.playerX = Player(data["name"], request.sid, "X")
    player = roomObj.playerX
    if roomObj.playerO != None:
      opponent = roomObj.playerO
    # if roomObj.playerO != None:
    #   opponent = roomObj.playerO
  else:
    roomObj.playerO = Player(data["name"], request.sid, "O")
    player = roomObj.playerO
    opponent = roomObj.playerX
  # ^ add client to room
  join_room(room, sid = request.sid)
  io.emit("connected_to_room", to=player.sid)
  # ^ move client into room
  print(prefix+"successfully connected client '"+request.sid+"' to room '"+data["room"]+"'")
  outgoing = None

  if current_user.is_authenticated:
    io.emit("wins_and_loses", {"wins": current_user.wins, "loses": current_user.loses}, to=request.sid)

  if opponent != None:
     
     outgoing = {"player": {"sid": player.sid, "name": player.name, "team": player.team}, 
                 "opponent": {"sid": opponent.sid, "name": opponent.name, "team": opponent.team}}
     io.emit("initialize_player", outgoing, to=player.sid)

     outgoing = {"opponent": {"sid": player.sid, "name": player.name, "team": player.team}}
     io.emit("initialize_player", outgoing, to=opponent.sid)
  else:
     outgoing = {"player": {"sid": player.sid, "name": player.name, "team": player.team}}
     io.emit("initialize_player", outgoing, to=player.sid)
  # ^ inform client about connection
     
@io.on("disconnect")
def handle_disconnect():
    socketsRooms = io.server.rooms(request.sid)
    for room in socketsRooms:
      if room != request.sid:
        
        if rooms[room].playerO != None:
          if rooms[room].playerO.sid == request.sid:
            print(prefix+rooms[room].playerO.name+" disconnected from room '"+room+"'")
            rooms[room].playerO = None
            io.emit("player_disconnected", to=room)
        if rooms[room].playerX != None:
          if rooms[room].playerX.sid == request.sid:
            print(prefix+rooms[room].playerX.name+" disconnected from room '"+room+"'")
            rooms[room].playerX = None
            io.emit("player_disconnected", to=room)
        if rooms[room].playerX != None: print(prefix+rooms[room].playerX.name+" remain in room")
        if rooms[room].playerO != None: print(prefix+rooms[room].playerO.name+" remain in room")
        if rooms[room].playerX == None and rooms[room].playerO == None:
          del rooms[room]
          

# PREGAME FUNCTIONS
# --------------------------------------------------------------------------------------------
@io.on("ready")
def set_player_ready(data):
  room = data["room"]
  sid = data["sid"]
  roomObj = rooms[room]

  if roomObj.playerX != None:
    if roomObj.playerX.sid == sid:
      roomObj.playerX.ready = True
    elif roomObj.playerO != None:
      if roomObj.playerO.sid == sid:
        roomObj.playerO.ready = True

  if roomObj.checkBothReady():
     if roomObj.lastTurn == "X":
        roomObj.turn = "O"
        
     if roomObj.lastTurn == "O":
        roomObj.turn = "X"
     roomObj.lastTurn = roomObj.turn

     io.emit("start_game", roomObj.turn, to=room)

# GAME UPDATES AND SIGNALS
# --------------------------------------------------------------------------------------------  

@io.on("game_move")
def handle_game_move(data):
  room =data["room"]
  roomObj = rooms[room]
  grid = data["grid"]
  team = data["team"]
  print(prefix+"Game move recieved in room '"+room+"'")

  # Handle incoming game move
  if (roomObj.turn == team):

    # ^ make sure move is submitted by turntaking client
    roomObj.grid = grid
    # ^ update grid of the room

    # if nobody winns, the checkWinCondition function returns None
    if roomObj.checkWinCondition() == None:

      if team == "X":
        recipient = roomObj.playerO.sid
      if team == "O":
        recipient = roomObj.playerX.sid
      
      roomObj.switchTurn()
      io.emit("game_update", {"grid": grid}, to=recipient)
    else:
      winner = roomObj.checkWinCondition()
      print(prefix+"Game ended in room '"+room+"'")
      roomObj.playerO.ready = False
      roomObj.playerX.ready = False

      if (winner == "X"):
        roomObj.playerX.wins += 1
        roomObj.playerO.loses += 1
      else:
        roomObj.playerX.loses += 1
        roomObj.playerO.wins += 1

      io.emit("win_update", {"grid": grid, "winner": winner}, to=room)
      roomObj.turn = None

@io.on("update_db")
def handle_db_update(win):
  if current_user.is_authenticated:
    if win:
      current_user.wins += 1
    else:
      current_user.loses += 1
    db.session.commit()
    print("[DataBase]: "+current_user.username+"'s wins: "+str(current_user.wins)+" loses: "+str(current_user.loses))
    io.emit("wins_and_loses", {"wins": current_user.wins, "loses": current_user.loses}, to=request.sid)

# CHAT
# --------------------------------------------------------------------------------------------    

@io.on("chat_message")
def handle_chat_message(data):
  room = data["room"]
  io.emit("chat_message", {"message": data["message"], "name": data["name"]}, to=room)
  # ^ send message from client back to all others in clients room
  print(prefix + "Deliver message '" + data["message"] + "' to room '" + room + "'")