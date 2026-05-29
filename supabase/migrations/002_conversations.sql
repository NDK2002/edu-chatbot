-- Migration 002: conversation management system
-- Adds conversations + messages tables (separate from legacy chat_sessions/chat_messages)

create table conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references profiles on delete cascade,
  title text not null default 'Cuộc trò chuyện mới',
  mode text check (mode in ('student','teacher')) default 'student',
  is_compacted boolean default false,
  compact_summary text,
  message_count int default 0,
  last_message_at timestamptz default now(),
  created_at timestamptz default now()
);

create table messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid references conversations on delete cascade,
  role text check (role in ('user','assistant')) not null,
  content text not null,
  query_type text,
  source text,
  is_compacted boolean default false,
  created_at timestamptz default now()
);

-- RLS
alter table conversations enable row level security;
alter table messages enable row level security;

create policy "Users manage own conversations"
  on conversations for all using (auth.uid() = user_id);

create policy "Users view own messages"
  on messages for all using (
    conversation_id in (
      select id from conversations where user_id = auth.uid()
    )
  );

-- Indexes for fast queries
create index on conversations (user_id, last_message_at desc);
create index on messages (conversation_id, created_at asc);
create index on messages (conversation_id, is_compacted);
