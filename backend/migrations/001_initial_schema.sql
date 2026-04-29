create table if not exists app_sessions (
    token text primary key,
    username text not null,
    created_at timestamptz not null
);

create table if not exists llm_profiles (
    id text primary key,
    data jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists projects (
    id text primary key,
    data jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists story_bibles (
    project_id text primary key references projects(id) on delete cascade,
    data jsonb not null,
    version integer not null default 1,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists serial_runs (
    id text primary key,
    project_id text not null references projects(id) on delete cascade,
    data jsonb not null,
    status text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_serial_runs_project_status on serial_runs(project_id, status);

create table if not exists run_events (
    id text primary key,
    serial_run_id text not null references serial_runs(id) on delete cascade,
    project_id text not null references projects(id) on delete cascade,
    data jsonb not null,
    event_type text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_run_events_run_created on run_events(serial_run_id, created_at);

create table if not exists chapter_plans (
    id text primary key,
    project_id text not null references projects(id) on delete cascade,
    serial_run_id text not null references serial_runs(id) on delete cascade,
    chapter_number integer not null,
    data jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_chapter_plans_project_chapter on chapter_plans(project_id, chapter_number);

create table if not exists chapter_drafts (
    id text primary key,
    project_id text not null references projects(id) on delete cascade,
    serial_run_id text not null references serial_runs(id) on delete cascade,
    chapter_number integer not null,
    version integer not null,
    status text not null,
    data jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists idx_chapter_drafts_version on chapter_drafts(project_id, chapter_number, version);
create index if not exists idx_chapter_drafts_project_status on chapter_drafts(project_id, status);

create table if not exists exports (
    id text primary key,
    project_id text not null references projects(id) on delete cascade,
    data jsonb not null,
    created_at timestamptz not null default now()
);

create table if not exists prompt_templates (
    id text primary key,
    data jsonb not null,
    is_default boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
