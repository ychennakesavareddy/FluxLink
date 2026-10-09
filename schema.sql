-- Supabase Schema for Chennalink

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Sessions Table
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_code VARCHAR(10) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    created_by VARCHAR(255)
);

-- Devices Table
CREATE TABLE devices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    device_name VARCHAR(255),
    device_type VARCHAR(50),
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(session_id, device_name)
);

-- Code Messages Table
CREATE TABLE code_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    sender_device_id UUID REFERENCES devices(id) ON DELETE SET NULL,
    receiver_device_id UUID REFERENCES devices(id) ON DELETE SET NULL,
    file_name VARCHAR(255) NOT NULL,
    language VARCHAR(50) DEFAULT 'python',
    content TEXT NOT NULL,
    message_type VARCHAR(50) DEFAULT 'code_file',
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Files Table (for versioning/persistence if needed)
CREATE TABLE files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    language VARCHAR(50) DEFAULT 'python',
    content TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_sessions_code ON sessions(session_code);
CREATE INDEX idx_devices_session ON devices(session_id);
CREATE INDEX idx_code_messages_session ON code_messages(session_id);
CREATE INDEX idx_code_messages_sender ON code_messages(sender_device_id);
CREATE INDEX idx_code_messages_receiver ON code_messages(receiver_device_id);
CREATE INDEX idx_code_messages_created_at ON code_messages(created_at);
