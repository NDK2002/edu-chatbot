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
  insert into public.profiles (id, username, display_name, role)
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
alter table saved_vocab enable row level security;

-- Policies: user chỉ xem/sửa data của chính mình
create policy "Users view own profile"
  on profiles for all using (auth.uid() = id);

create policy "Users manage own vocab"
  on saved_vocab for all using (auth.uid() = user_id);
