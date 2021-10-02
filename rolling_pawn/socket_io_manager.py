class SocketIOManager:
    def __init__(self, socket_io):
        self.socket_io = socket_io
        self.sessions_by_user = dict()
        self.user_by_session = dict()
        self.game_watchers = dict()

    def broadcast(self, event, data):
        self.socket_io.emit(event, data, broadcast=True)

    def add_session(self, session_id, user_id):
        if user_id not in self.sessions_by_user:
            self.sessions_by_user[user_id] = set()

        self.user_by_session[session_id] = user_id
        self.sessions_by_user[user_id].add(session_id)

    def add_watcher_session(self, session_id, game_id):
        self.game_watchers[game_id] = set()
        self.game_watchers[game_id].add(session_id)

    def emit_to_user(self, user_id, event, data):
        if user_id not in self.sessions_by_user:
            return
        for session_id in self.sessions_by_user[user_id]:
            self.socket_io.emit(event, data, to=session_id)

    def emit_to_watchers(self, game_id, event, data):
        if game_id not in self.game_watchers:
            return
        for session_id in self.game_watchers[game_id]:
            self.socket_io.emit(event, data, to=session_id)

    def remove_session(self, session_id):
        if session_id in self.user_by_session:
            user_id = self.user_by_session[session_id]
            self.sessions_by_user[user_id].remove(session_id)
            self.user_by_session.pop(session_id)
