create table lesson_plans (
  id         uuid    primary key default gen_random_uuid(),
  user_id    uuid    references profiles on delete cascade,
  topic      text    not null,
  grade      int     not null,
  subject    text    not null,
  objectives text[],
  activities jsonb,
  exercises  text[],
  rag_used   boolean default false,
  created_at timestamptz default now()
);

alter table lesson_plans enable row level security;

create policy "Teachers manage own lesson plans"
  on lesson_plans for all using (auth.uid() = user_id);
