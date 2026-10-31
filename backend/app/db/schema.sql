-- 谈心小辅 · 语音对话模块
-- 建表脚本，严格照《技术设计文档》7.1 节 DDL
-- 启动时执行本文件即可（CREATE TABLE IF NOT EXISTS，可重复跑）

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cases (
  id             TEXT PRIMARY KEY,
  version        INTEGER NOT NULL DEFAULT 1,
  category       TEXT NOT NULL CHECK (category IN ('academic','emotion','relationship','family','career','risk')),
  label          TEXT NOT NULL,
  public_json    TEXT NOT NULL,
  private_json   TEXT NOT NULL,
  review_status  TEXT NOT NULL DEFAULT 'draft' CHECK (review_status IN ('draft','reviewed')),
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  id             TEXT PRIMARY KEY,
  case_id        TEXT NOT NULL REFERENCES cases(id),
  case_version   INTEGER NOT NULL,
  prep_note      TEXT,
  status         TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created','active','ended')),
  created_at     TEXT NOT NULL,
  ended_at       TEXT,
  prev_session_id TEXT
);

CREATE TABLE IF NOT EXISTS turns (
  session_id     TEXT NOT NULL REFERENCES sessions(id),
  turn_no        INTEGER NOT NULL,
  role           TEXT NOT NULL CHECK (role IN ('teacher','student')),
  text           TEXT NOT NULL,
  source         TEXT NOT NULL DEFAULT 'text' CHECK (source IN ('text','asr','manual')),
  created_at     TEXT NOT NULL,
  PRIMARY KEY (session_id, turn_no)
);

CREATE TABLE IF NOT EXISTS request_log (
  idempotency_key TEXT PRIMARY KEY,
  session_id      TEXT NOT NULL,
  request_hash    TEXT NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('pending','done','failed')),
  turn_no         INTEGER,
  response_json   TEXT,
  tokens_in       INTEGER,
  tokens_out      INTEGER,
  latency_ms      INTEGER,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turns_session   ON turns(session_id, turn_no);
CREATE INDEX IF NOT EXISTS idx_sessions_case   ON sessions(case_id, created_at);
CREATE INDEX IF NOT EXISTS idx_request_status  ON request_log(status, created_at);
