-- Private, immutable-by-default plan snapshots. Clients may edit/delete only their own rows.
begin;
create table public.creator_plans (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    title text not null check (char_length(title) between 1 and 200),
    payload jsonb not null check (jsonb_typeof(payload) = 'object' and octet_length(payload::text) <= 262144),
    created_at timestamptz not null default now()
);
create index creator_plans_user_created_idx on public.creator_plans(user_id, created_at desc);
alter table public.creator_plans enable row level security;
alter table public.creator_plans force row level security;
revoke all on public.creator_plans from anon, authenticated;
grant select, insert, update, delete on public.creator_plans to authenticated;
create policy creator_plans_select on public.creator_plans for select to authenticated
    using ((select auth.uid()) = user_id);
create policy creator_plans_insert on public.creator_plans for insert to authenticated
    with check ((select auth.uid()) = user_id);
create policy creator_plans_update on public.creator_plans for update to authenticated
    using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy creator_plans_delete on public.creator_plans for delete to authenticated
    using ((select auth.uid()) = user_id);
commit;
