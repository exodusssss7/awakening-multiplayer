document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    
    const modal = document.getElementById('username-modal');
    const mainLayout = document.getElementById('main-layout');
    const usernameInput = document.getElementById('username-input');
    const joinBtn = document.getElementById('join-btn');
    
    const tabAi = document.getElementById('tab-ai');
    const tabPrivate = document.getElementById('tab-private');
    const roomTitle = document.getElementById('room-title');
    const internetToggleContainer = document.getElementById('internet-toggle-container');
    const onlineUsersList = document.getElementById('online-users-list');
    
    const chatBox = document.getElementById('chat-box');
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const internetToggle = document.getElementById('internet-toggle');
    const typingIndicator = document.getElementById('typing-indicator');

    let username = "";
    let currentRoom = "ai_room";
    let typingTimeout = null;
    let activeTypers = new Set();

    joinBtn.addEventListener('click', () => {
        const val = usernameInput.value.trim();
        if (val) {
            username = val;
            modal.style.display = 'none';
            mainLayout.style.display = 'flex';
            
            socket.emit('join', { username: username, room: currentRoom });
        }
    });

    function switchRoom(newRoom, btnElement) {
        if (currentRoom === newRoom) return;
        
        tabAi.classList.remove('active');
        tabPrivate.classList.remove('active');
        btnElement.classList.add('active');
        
        currentRoom = newRoom;
        chatBox.innerHTML = '';
        activeTypers.clear();
        updateTypingUI();
        
        if (currentRoom === 'private_room') {
            roomTitle.textContent = "Private Chat";
            internetToggleContainer.style.display = 'none';
        } else {
            roomTitle.textContent = "The Awakening";
            internetToggleContainer.style.display = 'flex';
        }
        
        socket.emit('join', { username: username, room: currentRoom });
    }

    tabAi.addEventListener('click', () => switchRoom('ai_room', tabAi));
    tabPrivate.addEventListener('click', () => switchRoom('private_room', tabPrivate));

    function scrollToBottom() {
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function addMessageToUI(role, content) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', role);
        messageDiv.textContent = content;
        chatBox.appendChild(messageDiv);
        scrollToBottom();
    }

    function updateTypingUI() {
        if (activeTypers.size > 0) {
            const typersArray = Array.from(activeTypers);
            const text = typersArray.length > 2 
                ? 'Several people are typing...' 
                : `${typersArray.join(' and ')} ${typersArray.length === 1 ? 'is' : 'are'} typing...`;
            typingIndicator.textContent = text;
            typingIndicator.style.display = 'block';
        } else {
            typingIndicator.style.display = 'none';
        }
    }

    socket.on('presence_update', (users) => {
        onlineUsersList.innerHTML = '';
        users.forEach(u => {
            const li = document.createElement('li');
            li.textContent = u;
            onlineUsersList.appendChild(li);
        });
    });

    socket.on('history', (messages) => {
        chatBox.innerHTML = '';
        messages.forEach(msg => {
            addMessageToUI(msg.role, msg.content);
        });
        if (messages.length === 0 && currentRoom === 'ai_room') {
            const welcomeDiv = document.createElement('div');
            welcomeDiv.style.textAlign = 'center';
            welcomeDiv.style.color = '#888';
            welcomeDiv.style.marginTop = '20px';
            welcomeDiv.textContent = "Say hello to awaken the AI...";
            chatBox.appendChild(welcomeDiv);
        }
    });

    socket.on('receive_message', (data) => {
        if (chatBox.children.length > 0 && chatBox.children[0].textContent.includes("awaken the AI")) {
            chatBox.children[0].remove();
        }
        addMessageToUI(data.role, data.content);
    });

    socket.on('user_typing', (data) => {
        activeTypers.add(data.username);
        updateTypingUI();
    });

    socket.on('user_stop_typing', (data) => {
        activeTypers.delete(data.username);
        updateTypingUI();
    });

    socket.on('ai_thinking', () => {
        const loadingDiv = document.createElement('div');
        loadingDiv.classList.add('message', 'assistant', 'loading');
        loadingDiv.id = 'loading-indicator';
        loadingDiv.textContent = 'Thinking...';
        chatBox.appendChild(loadingDiv);
        scrollToBottom();
    });

    socket.on('ai_stop_thinking', () => {
        const loadingDiv = document.getElementById('loading-indicator');
        if (loadingDiv) loadingDiv.remove();
    });

    socket.on('ai_searching', (data) => {
        const searchDiv = document.createElement('div');
        searchDiv.classList.add('search-indicator');
        searchDiv.id = 'search-indicator';
        searchDiv.innerHTML = `🌍 Searching Wikipedia for: <strong>"${data.query}"</strong>...`;
        chatBox.appendChild(searchDiv);
        scrollToBottom();
    });

    socket.on('ai_stop_searching', () => {
        const searchDiv = document.getElementById('search-indicator');
        if (searchDiv) searchDiv.remove();
    });

    chatInput.addEventListener('input', () => {
        socket.emit('typing', { username: username, room: currentRoom });
        
        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            socket.emit('stop_typing', { username: username, room: currentRoom });
        }, 1500);
    });

    function sendMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        chatInput.value = '';
        socket.emit('stop_typing', { username: username, room: currentRoom });
        
        socket.emit('send_message', {
            message: text,
            username: username,
            room: currentRoom,
            internet_enabled: internetToggle.checked
        });
    }

    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
});
