-- CogScheduler: Supabase schema migration
-- Run this in the Supabase SQL Editor: https://supabase.com/dashboard → SQL Editor

-- 1. Users table
CREATE TABLE IF NOT EXISTS public.users (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  google_id  TEXT UNIQUE NOT NULL,
  email      TEXT NOT NULL DEFAULT '',
  name       TEXT NOT NULL DEFAULT '',
  avatar_url TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Profiles table
CREATE TABLE IF NOT EXISTS public.profiles (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID UNIQUE NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  role                 TEXT DEFAULT 'student',
  chronotype           TEXT DEFAULT 'normal',
  wake_time            TEXT DEFAULT '07:00',
  sleep_time           TEXT DEFAULT '23:00',
  sleep_hours          REAL DEFAULT 7.0,
  stress_level         INT DEFAULT 2,
  daily_commitments    JSONB DEFAULT '[]'::jsonb,
  break_preferences    JSONB DEFAULT '[]'::jsonb,
  lectures_today       INT DEFAULT 0,
  timetable_data       JSONB DEFAULT '{}'::jsonb,
  occupation           TEXT DEFAULT '',
  work_hours           TEXT DEFAULT '',
  meetings_today       INT DEFAULT 0,
  occupation_busy_slots JSONB DEFAULT '[]'::jsonb,
  has_timetable        BOOLEAN DEFAULT FALSE,
  timetable_answers    JSONB DEFAULT '{}'::jsonb,
  updated_at           TIMESTAMPTZ DEFAULT now()
);

-- 3. Schedules table
CREATE TABLE IF NOT EXISTS public.schedules (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  schedule_data   JSONB DEFAULT '{}'::jsonb,
  created_at      TIMESTAMPTZ DEFAULT now(),
  calendar_synced BOOLEAN DEFAULT FALSE
);

-- 4. Indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_google_id     ON public.users(google_id);
CREATE INDEX IF NOT EXISTS idx_profiles_user_id    ON public.profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_schedules_user_id   ON public.schedules(user_id);
CREATE INDEX IF NOT EXISTS idx_schedules_created   ON public.schedules(created_at DESC);

-- 5. Row Level Security (allow anon key full access for now — tighten later)
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.schedules ENABLE ROW LEVEL SECURITY;

-- Allow all operations via anon/service key
CREATE POLICY "Allow all on users"     ON public.users     FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on profiles"  ON public.profiles  FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on schedules" ON public.schedules FOR ALL USING (true) WITH CHECK (true);

-- Done!
SELECT 'CogScheduler tables created successfully!' AS status;
