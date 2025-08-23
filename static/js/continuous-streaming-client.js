class ContinuousStreamingClient {
    constructor(serverUrl) {
        this.serverUrl = serverUrl;
        this.websocket = null;
        this.isConnected = false;
        this.isStreaming = false;
        this.audioContext = null;
        this.mediaRecorder = null;
        this.audioManager = null;
        this.chunkCounter = 0;
        
        // Event handlers
        this.onConnected = () => {};
        this.onDisconnected = () => {};
        this.onError = (error) => {console.error(error)};
        this.onTranscript = (text, isUser) => {};
        this.onAudioChunk = (chunk) => {};
    }
    
    async connect() {
        try {
            this.websocket = new WebSocket(this.serverUrl);
            
            this.websocket.onopen = async () => {
                console.log("WebSocket connection established");
                // Send authentication data
                this.websocket.send(JSON.stringify({
                    userId: "user-" + Date.now(),
                    authToken: "demo-token"
                }));
            };
            
            this.websocket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                switch(data.type) {
                    case "connection_ready":
                        this.isConnected = true;
                        this.onConnected();
                        break;
                        
                    case "streaming_paused":
                        this.isStreaming = false;
                        break;
                        
                    case "streaming_resumed":
                        this.isStreaming = true;
                        break;
                        
                    case "input_transcript":
                        this.onTranscript(data.text, true);
                        break;
                        
                    case "output_transcript":
                        this.onTranscript(data.text, false);
                        break;
                        
                    case "audio_chunk":
                        this.onAudioChunk(data);
                        this.sendAckForChunk(data.chunk_id);
                        break;
                        
                    case "error":
                        this.onError(data.message);
                        break;
                }
            };
            
            this.websocket.onclose = () => {
                this.isConnected = false;
                this.isStreaming = false;
                this.onDisconnected();
                console.log("WebSocket connection closed");
            };
            
            this.websocket.onerror = (error) => {
                this.onError("WebSocket error: " + error);
            };
            
        } catch (error) {
            this.onError("Connection error: " + error);
        }
    }
    
    async startStreaming() {
        if (!this.isConnected) {
            this.onError("Cannot start streaming: not connected");
            return;
        }
        
        try {
            // Initialize audio context and stream if not already done
            if (!this.audioContext) {
                this.audioContext = new AudioContext({sampleRate: 16000});
                this.audioManager = new LiveAudioInputManager();
                this.audioManager.onNewAudioRecordingChunk = (audioData) => {
                    this.sendAudioChunk(audioData);
                };
                await this.audioManager.connectMicrophone();
            }
            
            // Tell server to resume streaming if paused
            this.websocket.send(JSON.stringify({
                command: "resume_streaming"
            }));
            
            this.isStreaming = true;
        } catch (error) {
            this.onError("Error starting audio stream: " + error);
        }
    }
    
    pauseStreaming() {
        if (this.isStreaming) {
            this.websocket.send(JSON.stringify({
                command: "pause_streaming"
            }));
        }
    }
    
    sendAudioChunk(audioData) {
        if (!this.isConnected || !this.isStreaming) return;
        
        // Convert base64 to binary
        const binaryData = this._base64ToBinary(audioData);
        
        // Send audio chunk
        this.websocket.send(binaryData);
    }
    
    sendAckForChunk(chunkId) {
        if (!this.isConnected) return;
        
        this.websocket.send(JSON.stringify({
            command: "client_ack",
            chunk_id: chunkId
        }));
    }
    
    disconnect() {
        if (this.isConnected) {
            this.websocket.send(JSON.stringify({
                command: "disconnect"
            }));
        }
        
        if (this.audioManager) {
            this.audioManager.disconnectMicrophone();
        }
        
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
    }
    
    _base64ToBinary(base64) {
        const raw = window.atob(base64);
        const rawLength = raw.length;
        const array = new Uint8Array(new ArrayBuffer(rawLength));
        
        for (let i = 0; i < rawLength; i++) {
            array[i] = raw.charCodeAt(i);
        }
        
        return array.buffer;
    }
}