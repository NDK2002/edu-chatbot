-- profiles: extend Supabase auth.users
create table profiles (
  id uuid references auth.users on delete cascade primary key,
  username text unique,
  display_name text,
  role text check (role in ('student','teacher')) default 'student',
  grade int check (grade between 1 and 9),
  school text,
  created_at timestamptz default now()
);

-- Tự động tạo profile khi user register
create or replace function handle_new_user()
returns trigger as $$
begin
  insert into profiles (id, username, display_name, role)
  values (new.id,
          new.raw_user_meta_data->>'username',
          new.raw_user_meta_data->>'display_name',
          coalesce(new.raw_user_meta_data->>'role', 'student'));
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure handle_new_user();

-- chat_sessions
create table chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references profiles on delete cascade,
  mode text check (mode in ('student','teacher')) default 'student',
  created_at timestamptz default now()
);

-- chat_messages
create table chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid references chat_sessions on delete cascade,
  role text check (role in ('user','assistant')),
  content text not null,
  query_type text,   -- MATH_CALCULATE, MATH_THEORY, DICT_VI_TAY, etc.
  source text,       -- rule_engine, vector_search, gemini
  created_at timestamptz default now()
);

-- saved_vocab
create table saved_vocab (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references profiles on delete cascade,
  vi text not null,
  tay_variants text[],
  nung_variants text[],
  saved_at timestamptz default now(),
  unique(user_id, vi)
);

-- RLS
alter table profiles enable row level security;
alter table chat_sessions enable row level security;
alter table chat_messages enable row level security;
alter table saved_vocab enable row level security;

-- Policies: user chỉ xem/sửa data của chính mình
create policy "Users view own profile"
  on profiles for all using (auth.uid() = id);

create policy "Users view own sessions"
  on chat_sessions for all using (auth.uid() = user_id);

create policy "Users view own messages"
  on chat_messages for all using (
    session_id in (select id from chat_sessions where user_id = auth.uid())
  );

create policy "Users manage own vocab"
  on saved_vocab for all using (auth.uid() = user_id);
