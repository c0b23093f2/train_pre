-- Supabase の SQL Editor に貼り付けて「Run」を押すと、merged.csv と同じ内容を入れる表ができます。
-- 何度実行しても壊れません（if not exists）。1日 × 1路線 = 1行。

create table if not exists merged_daily (
    date            date    not null,
    line            text    not null,
    -- 遅延（分）。0 = 遅延なし、61 = 61分以上
    d_start_7       integer,     -- 始発～7時
    d_7_10          integer,     -- 7時～10時
    d_10_16         integer,     -- 10時～16時
    d_16_21         integer,     -- 16時～21時
    d_21_end        integer,     -- 21時～終電
    max_delay       integer,
    total_delay     integer,
    -- 気象（地点ごと）。観測していない項目は NULL
    tokyo_snow_cm       real,  tokyo_precip_mm     real,  tokyo_temp_c     real,
    tokyo_wind_ms       real,  tokyo_vapor_hpa     real,  tokyo_cloud      real,
    hachioji_snow_cm    real,  hachioji_precip_mm  real,  hachioji_temp_c  real,
    hachioji_wind_ms    real,  hachioji_vapor_hpa  real,  hachioji_cloud   real,
    setagaya_snow_cm    real,  setagaya_precip_mm  real,  setagaya_temp_c  real,
    setagaya_wind_ms    real,  setagaya_vapor_hpa  real,  setagaya_cloud   real,
    ome_snow_cm         real,  ome_precip_mm       real,  ome_temp_c       real,
    ome_wind_ms         real,  ome_vapor_hpa       real,  ome_cloud        real,
    updated_at      timestamptz not null default now(),
    primary key (date, line)     -- 同じ日・同じ路線は1行だけ（重複防止）
);

-- 行レベルセキュリティ（RLS）を有効にする。ポリシーは作らないので、
-- 公開用のキーでは読み書きできません。アプリは Secret key（sb_secret_...）で接続します。
alter table merged_daily enable row level security;
