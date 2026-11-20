-- Eligibility batches and fuzzy regression-discontinuity reports.
-- Startup still uses metadata.create_all; this file documents the canonical DDL.
CREATE TABLE IF NOT EXISTS eligibility_batches (
  id SERIAL PRIMARY KEY,
  title VARCHAR(120) UNIQUE NOT NULL,
  term VARCHAR(80) NOT NULL DEFAULT '',
  threshold FLOAT NOT NULL,
  direction VARCHAR(10) NOT NULL DEFAULT 'gte',
  bandwidth FLOAT,
  bandwidth_rule VARCHAR(60) NOT NULL DEFAULT 'auto_min_side_n',
  bandwidth_basis JSON,
  min_side_n INTEGER NOT NULL DEFAULT 5,
  min_side_distinct INTEGER NOT NULL DEFAULT 5,
  min_participation_jump FLOAT NOT NULL DEFAULT 0.2,
  status VARCHAR(20) NOT NULL DEFAULT 'draft',
  revision INTEGER NOT NULL DEFAULT 0,
  lock_token VARCHAR(64),
  lock_started_at VARCHAR(40),
  locked_at VARCHAR(40),
  roster_checksum VARCHAR(64) NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  created_at VARCHAR(40) NOT NULL DEFAULT '',
  updated_at VARCHAR(40) NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS eligibility_candidates (
  id SERIAL PRIMARY KEY,
  batch_id INTEGER NOT NULL REFERENCES eligibility_batches(id),
  student_id INTEGER NOT NULL REFERENCES students(id),
  enrollment_score FLOAT NOT NULL,
  created_at VARCHAR(40) NOT NULL DEFAULT '',
  updated_at VARCHAR(40) NOT NULL DEFAULT '',
  CONSTRAINT uq_eligibility_candidate UNIQUE (batch_id, student_id)
);
CREATE TABLE IF NOT EXISTS eligibility_roster_entries (
  id SERIAL PRIMARY KEY,
  batch_id INTEGER NOT NULL REFERENCES eligibility_batches(id),
  student_id INTEGER NOT NULL REFERENCES students(id),
  enrollment_score FLOAT NOT NULL,
  eligible BOOLEAN NOT NULL DEFAULT FALSE,
  created_at VARCHAR(40) NOT NULL DEFAULT '',
  CONSTRAINT uq_eligibility_roster UNIQUE (batch_id, student_id)
);
CREATE TABLE IF NOT EXISTS participation_records (
  id SERIAL PRIMARY KEY,
  batch_id INTEGER NOT NULL REFERENCES eligibility_batches(id),
  student_id INTEGER NOT NULL REFERENCES students(id),
  participated BOOLEAN NOT NULL DEFAULT FALSE,
  note TEXT NOT NULL DEFAULT '',
  updated_by VARCHAR(120) NOT NULL DEFAULT '',
  updated_at VARCHAR(40) NOT NULL DEFAULT '',
  CONSTRAINT uq_participation_record UNIQUE (batch_id, student_id)
);
CREATE TABLE IF NOT EXISTS eligibility_corrections (
  id SERIAL PRIMARY KEY,
  batch_id INTEGER NOT NULL REFERENCES eligibility_batches(id),
  student_id INTEGER REFERENCES students(id),
  field VARCHAR(40) NOT NULL,
  old_value TEXT NOT NULL DEFAULT '',
  new_value TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  actor VARCHAR(120) NOT NULL DEFAULT '',
  resulting_revision INTEGER NOT NULL DEFAULT 0,
  created_at VARCHAR(40) NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS rd_reports (
  id SERIAL PRIMARY KEY,
  batch_id INTEGER NOT NULL REFERENCES eligibility_batches(id),
  status VARCHAR(20) NOT NULL DEFAULT 'queued',
  batch_revision INTEGER NOT NULL DEFAULT 0,
  result JSON,
  error TEXT NOT NULL DEFAULT '',
  conclusion TEXT NOT NULL DEFAULT '',
  published BOOLEAN NOT NULL DEFAULT FALSE,
  valid BOOLEAN NOT NULL DEFAULT TRUE,
  invalidated_reason TEXT NOT NULL DEFAULT '',
  invalidated_at VARCHAR(40),
  computed_at VARCHAR(40),
  recomputed_from_id INTEGER,
  created_at VARCHAR(40) NOT NULL DEFAULT ''
);
