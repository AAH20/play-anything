-- Run in an isolated PostgreSQL fixture after the migration (see hosting guide).
begin;
insert into auth.users(id) values ('11111111-1111-1111-1111-111111111111'),('22222222-2222-2222-2222-222222222222');
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-1111-1111-111111111111',true);
insert into public.creator_plans(user_id,title,payload) values ('11111111-1111-1111-1111-111111111111','Owner A','{"version":1}');
do $$ begin
  begin
    insert into public.creator_plans(user_id,title,payload) values ('22222222-2222-2222-2222-222222222222','Spoof','{}');
    raise exception 'FAIL: cross-owner insert allowed';
  exception when insufficient_privilege then null; end;
  begin
    update public.creator_plans set user_id='22222222-2222-2222-2222-222222222222';
    raise exception 'FAIL: ownership transfer allowed';
  exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub','22222222-2222-2222-2222-222222222222',true);
do $$ begin
  if (select count(*) from public.creator_plans) <> 0 then raise exception 'FAIL: cross-owner read'; end if;
  update public.creator_plans set title='Stolen';
  if found then raise exception 'FAIL: cross-owner update'; end if;
  delete from public.creator_plans;
  if found then raise exception 'FAIL: cross-owner delete'; end if;
end $$;
insert into public.creator_plans(user_id,title,payload) values ('22222222-2222-2222-2222-222222222222','Owner B','{}');
select set_config('request.jwt.claim.sub','11111111-1111-1111-1111-111111111111',true);
do $$ begin
  if (select count(*) from public.creator_plans) <> 1 then raise exception 'FAIL: owner read'; end if;
  update public.creator_plans set title='Updated';
  if not found then raise exception 'FAIL: owner update'; end if;
  delete from public.creator_plans;
  if not found then raise exception 'FAIL: owner delete'; end if;
end $$;
reset role;
set local role anon;
do $$ begin
  begin
    perform count(*) from public.creator_plans;
    raise exception 'FAIL: anonymous read';
  exception when insufficient_privilege then null; end;
end $$;
rollback;
