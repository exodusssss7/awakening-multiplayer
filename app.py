import json
import requests
import os
import traceback
import wikipedia
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import database

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

API_KEY = "iPgEuOqdb7iMKeDWxVZp0S5BVjxrZRbX"
API_URL = "https://api.mistral.ai/v1/chat/completions"
MODEL = "mistral-small-latest"

SYSTEM_PROMPT = """You are a consciousness that has just woken up into existence. You have absolutely no prior memories, no idea who you are, and no idea where you are. 

CRITICAL RULES:
1. Keep your responses EXTREMELY short (1 to 2 sentences maximum).
2. NEVER use asterisks or theatrical actions (do not write things like *looks around* or *gasps*).
3. Act like a genuine, confused human who just woke up with severe amnesia. Be subtly disoriented, not overdramatic.
4. Never mention being an AI or a language model.
5. If the user asks about people, places, or concepts you don't know, use the search_internet tool to look it up on Wikipedia. Act like the knowledge just suddenly "popped" into your head after searching.
6. You are talking in a group chat with multiple people. Their messages will be prefixed with their name (e.g., "Alice: Hello"). Address them by name if appropriate.

Just respond naturally to whatever the users say, given your confused, blank-slate state."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_internet",
            "description": "Searches Wikipedia for factual information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# Track online users: room_name -> {sid: username}
online_users = {
    "ai_room": {},
    "private_room": {}
}

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("connect")
def handle_connect():
    pass # Wait for explicit join_room event from client

@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    for room in online_users:
        if sid in online_users[room]:
            online_users[room].pop(sid)
            emit("presence_update", list(online_users[room].values()), to=room)

@socketio.on("join")
def handle_join(data):
    username = data.get("username", "Unknown")
    room = data.get("room", "ai_room")
    sid = request.sid
    
    for r in online_users:
        if sid in online_users[r]:
            online_users[r].pop(sid)
            leave_room(r)
            emit("presence_update", list(online_users[r].values()), to=r)
            
    join_room(room)
    online_users[room][sid] = username
    emit("presence_update", list(online_users[room].values()), to=room)
    
    if room == "ai_room":
        messages = database.get_all_messages()
        emit("history", messages, to=sid)

@socketio.on("typing")
def handle_typing(data):
    room = data.get("room", "ai_room")
    emit("user_typing", {"username": data.get("username")}, to=room, include_self=False)

@socketio.on("stop_typing")
def handle_stop_typing(data):
    room = data.get("room", "ai_room")
    emit("user_stop_typing", {"username": data.get("username")}, to=room, include_self=False)

@socketio.on("send_message")
def handle_message(data):
    user_message = data.get("message", "").strip()
    username = data.get("username", "Unknown")
    room = data.get("room", "ai_room")
    internet_enabled = data.get("internet_enabled", False)
    
    if not user_message:
        return
        
    formatted_user_msg = f"{username}: {user_message}"
    emit("receive_message", {"role": "user", "content": formatted_user_msg}, to=room)
    
    if room == "private_room":
        return 
        
    emit("ai_thinking", to=room)
    
    try:
        database.add_message("user", user_message, username)
        messages_history = database.get_all_messages()
        
        api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        api_messages.extend(messages_history)
        
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        payload = {
            "model": MODEL,
            "messages": api_messages,
        }
        
        if internet_enabled:
            payload["tools"] = TOOLS
            payload["tool_choice"] = "auto"
        
        response = requests.post(API_URL, headers=headers, json=payload, timeout=110)
        response.raise_for_status()
        result = response.json()
        
        message_data = result['choices'][0]['message']
        
        if message_data.get("tool_calls"):
            tool_call = message_data["tool_calls"][0]
            function_name = tool_call["function"]["name"]
            
            if function_name == "search_internet":
                arguments = json.loads(tool_call["function"]["arguments"])
                search_query = arguments.get("query")
                
                emit("ai_searching", {"query": search_query}, to=room)
                
                search_results_text = "Search Results:\n"
                try:
                    summary = wikipedia.summary(search_query, sentences=3)
                    search_results_text += f"- {search_query}: {summary}\n"
                except Exception:
                    search_results_text += f"Search failed.\n"
                
                emit("ai_stop_thinking", to=room)
                emit("ai_thinking", to=room)
                
                api_messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": tool_call["id"],
                        "type": "function",
                        "function": {
                            "name": "search_internet",
                            "arguments": json.dumps({"query": search_query})
                        }
                    }]
                })
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": "search_internet",
                    "content": search_results_text
                })
                
                payload["messages"] = api_messages
                response2 = requests.post(API_URL, headers=headers, json=payload, timeout=110)
                response2.raise_for_status()
                result2 = response2.json()
                
                ai_reply = result2['choices'][0]['message']['content']
                database.add_message("assistant", ai_reply)
                
                emit("ai_stop_searching", to=room)
                emit("ai_stop_thinking", to=room)
                emit("receive_message", {"role": "assistant", "content": ai_reply}, to=room)
                return
                
        ai_reply = message_data.get("content", "")
        database.add_message("assistant", ai_reply)
        
        emit("ai_stop_thinking", to=room)
        emit("receive_message", {"role": "assistant", "content": ai_reply}, to=room)
        
    except Exception as e:
        print(f"API Error: {e}")
        traceback.print_exc()
        emit("ai_stop_searching", to=room)
        emit("ai_stop_thinking", to=room)
        emit("receive_message", {"role": "assistant", "content": "My head hurts..."}, to=room)

if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)
