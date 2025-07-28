--
-- PostgreSQL database dump
--

-- Dumped from database version 17.4
-- Dumped by pg_dump version 17.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: core_tables; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA core_tables;


ALTER SCHEMA core_tables OWNER TO postgres;

--
-- Name: join_tables; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA join_tables;


ALTER SCHEMA join_tables OWNER TO postgres;

--
-- Name: ranking_tables; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA ranking_tables;


ALTER SCHEMA ranking_tables OWNER TO postgres;

--
-- Name: track_tables; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA track_tables;


ALTER SCHEMA track_tables OWNER TO postgres;

--
-- Name: modeflag; Type: TYPE; Schema: track_tables; Owner: postgres
--

CREATE TYPE track_tables.modeflag AS ENUM (
    'SOLO',
    'DUET',
    'FEATURED',
    'GROUP',
    'UNKNOWN'
);


ALTER TYPE track_tables.modeflag OWNER TO postgres;

--
-- Name: create_filtered_view(text, text); Type: FUNCTION; Schema: ranking_tables; Owner: postgres
--

CREATE FUNCTION ranking_tables.create_filtered_view(p_genre text, p_decade text) RETURNS void
    LANGUAGE plpgsql
    AS $_$
DECLARE
    view_name TEXT;
    sql TEXT;
BEGIN
    -- Generate a view name like: vw_trackranking_country_1950s
    view_name := format(
        'vw_trackranking_%s_%s',
        lower(p_genre),
        lower(replace(p_decade, ' ', ''))
    );

    -- Create dynamic SQL for the view
    sql := format(
        $f$
        CREATE OR REPLACE VIEW rankings_tables.%I AS
        SELECT *
        FROM rankings_tables.vw_trackranking_details
        WHERE genre = %L
          AND decade = %L
        ORDER BY rank;
        $f$,
        view_name, p_genre, p_decade
    );

    -- Run the generated SQL
    EXECUTE sql;
END;
$_$;


ALTER FUNCTION ranking_tables.create_filtered_view(p_genre text, p_decade text) OWNER TO postgres;

--
-- Name: get_top_tracks(text, text); Type: FUNCTION; Schema: ranking_tables; Owner: postgres
--

CREATE FUNCTION ranking_tables.get_top_tracks(_genre text, _decade text) RETURNS TABLE(rank integer, track_name text, artist_name text, genre text, decade text)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT r.rank, t.name, a.name, g.name, d.name
    FROM rankings_tables.trackranking r
    JOIN core_tables.track t ON r.track_id = t.id
    JOIN core_tables.artist a ON t.artist_id = a.id
    JOIN core_tables.genre g ON t.genre_id = g.id
    JOIN join_tables.decadegenre dg ON r.decadegenre_id = dg.id
    JOIN core_tables.decade d ON dg.decade_id = d.id
    WHERE g.name = _genre AND d.name = _decade
    ORDER BY r.rank;
END;
$$;


ALTER FUNCTION ranking_tables.get_top_tracks(_genre text, _decade text) OWNER TO postgres;

--
-- Name: gettopartistsbygenre(text); Type: FUNCTION; Schema: ranking_tables; Owner: postgres
--

CREATE FUNCTION ranking_tables.gettopartistsbygenre(_genre text) RETURNS TABLE(rank integer, artistname text, trackname text, genre text)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT 
        v.rank,
        v.artistname,
        v.trackname,
        v.genre
    FROM rankings_tables.vwTopArtistGenreRankingDetails v
    WHERE v.genre ILIKE _genre
    ORDER BY v.rank;
END;
$$;


ALTER FUNCTION ranking_tables.gettopartistsbygenre(_genre text) OWNER TO postgres;

--
-- Name: gettopspecialtytracks(text); Type: FUNCTION; Schema: ranking_tables; Owner: postgres
--

CREATE FUNCTION ranking_tables.gettopspecialtytracks(_specialty text) RETURNS TABLE(rank integer, trackname text, artistname text, specialty text)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT 
        v.rank, 
        v.trackname, 
        v.artistname, 
        v.specialty
    FROM rankings_tables.vwSpecialtyRankingDetails v
    WHERE v.specialty ILIKE _specialty
    ORDER BY v.rank;
END;
$$;


ALTER FUNCTION ranking_tables.gettopspecialtytracks(_specialty text) OWNER TO postgres;

--
-- Name: gettracksbyartist(integer); Type: FUNCTION; Schema: ranking_tables; Owner: postgres
--

CREATE FUNCTION ranking_tables.gettracksbyartist(_artistid integer) RETURNS TABLE(rank integer, trackname text, artistname text, genre text, decade text)
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN QUERY
    SELECT 
        v.rank, 
        v.trackname, 
        v.artistname, 
        v.genre, 
        v.decade
    FROM rankings_tables.vwArtistTrackRankingDetails v
    WHERE v.artistid = _artistid
    ORDER BY v.rank;
END;
$$;


ALTER FUNCTION ranking_tables.gettracksbyartist(_artistid integer) OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: artist; Type: TABLE; Schema: core_tables; Owner: postgres
--

CREATE TABLE core_tables.artist (
    id integer NOT NULL,
    artist_name text NOT NULL,
    spotify_artist_id text,
    artist_artwork text,
    artist_description text,
    not_on_spotify boolean DEFAULT false
);


ALTER TABLE core_tables.artist OWNER TO postgres;

--
-- Name: COLUMN artist.artist_artwork; Type: COMMENT; Schema: core_tables; Owner: postgres
--

COMMENT ON COLUMN core_tables.artist.artist_artwork IS 'URL to the artist''s image or artwork (from Spotify or other source).';


--
-- Name: artist_id_seq; Type: SEQUENCE; Schema: core_tables; Owner: postgres
--

CREATE SEQUENCE core_tables.artist_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core_tables.artist_id_seq OWNER TO postgres;

--
-- Name: artist_id_seq; Type: SEQUENCE OWNED BY; Schema: core_tables; Owner: postgres
--

ALTER SEQUENCE core_tables.artist_id_seq OWNED BY core_tables.artist.id;


--
-- Name: core_schema_summary; Type: VIEW; Schema: core_tables; Owner: postgres
--

CREATE VIEW core_tables.core_schema_summary AS
 SELECT table_schema,
    table_name,
    column_name,
    data_type
   FROM information_schema.columns
  WHERE ((table_schema)::name = ANY (ARRAY['core_tables'::name, 'track_tables'::name, 'join_tables'::name, 'ranking_tables'::name]))
  ORDER BY table_schema, table_name, ordinal_position;


ALTER VIEW core_tables.core_schema_summary OWNER TO postgres;

--
-- Name: decade; Type: TABLE; Schema: core_tables; Owner: postgres
--

CREATE TABLE core_tables.decade (
    id integer NOT NULL,
    decade_name text NOT NULL,
    display_name text
);


ALTER TABLE core_tables.decade OWNER TO postgres;

--
-- Name: decade_id_seq; Type: SEQUENCE; Schema: core_tables; Owner: postgres
--

CREATE SEQUENCE core_tables.decade_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core_tables.decade_id_seq OWNER TO postgres;

--
-- Name: decade_id_seq; Type: SEQUENCE OWNED BY; Schema: core_tables; Owner: postgres
--

ALTER SEQUENCE core_tables.decade_id_seq OWNED BY core_tables.decade.id;


--
-- Name: genre; Type: TABLE; Schema: core_tables; Owner: postgres
--

CREATE TABLE core_tables.genre (
    id integer NOT NULL,
    genre_name text NOT NULL,
    display_name text
);


ALTER TABLE core_tables.genre OWNER TO postgres;

--
-- Name: genre_id_seq; Type: SEQUENCE; Schema: core_tables; Owner: postgres
--

CREATE SEQUENCE core_tables.genre_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core_tables.genre_id_seq OWNER TO postgres;

--
-- Name: genre_id_seq; Type: SEQUENCE OWNED BY; Schema: core_tables; Owner: postgres
--

ALTER SEQUENCE core_tables.genre_id_seq OWNED BY core_tables.genre.id;


--
-- Name: language; Type: TABLE; Schema: core_tables; Owner: postgres
--

CREATE TABLE core_tables.language (
    code character varying NOT NULL,
    name character varying NOT NULL
);


ALTER TABLE core_tables.language OWNER TO postgres;

--
-- Name: specialty; Type: TABLE; Schema: core_tables; Owner: postgres
--

CREATE TABLE core_tables.specialty (
    id integer NOT NULL,
    specialty_name text NOT NULL,
    display_name text
);


ALTER TABLE core_tables.specialty OWNER TO postgres;

--
-- Name: specialty_id_seq; Type: SEQUENCE; Schema: core_tables; Owner: postgres
--

CREATE SEQUENCE core_tables.specialty_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core_tables.specialty_id_seq OWNER TO postgres;

--
-- Name: specialty_id_seq; Type: SEQUENCE OWNED BY; Schema: core_tables; Owner: postgres
--

ALTER SEQUENCE core_tables.specialty_id_seq OWNED BY core_tables.specialty.id;


--
-- Name: vw_decade_genre_specialty; Type: VIEW; Schema: core_tables; Owner: postgres
--

CREATE VIEW core_tables.vw_decade_genre_specialty AS
 SELECT d.name AS decade,
    g.name AS genre,
    s.name AS specialty
   FROM ((( SELECT decade.decade_name AS name,
            row_number() OVER () AS rn
           FROM core_tables.decade) d
     FULL JOIN ( SELECT genre.genre_name AS name,
            row_number() OVER () AS rn
           FROM core_tables.genre) g ON ((d.rn = g.rn)))
     FULL JOIN ( SELECT specialty.specialty_name AS name,
            row_number() OVER () AS rn
           FROM core_tables.specialty) s ON ((COALESCE(d.rn, g.rn) = s.rn)));


ALTER VIEW core_tables.vw_decade_genre_specialty OWNER TO postgres;

--
-- Name: VIEW vw_decade_genre_specialty; Type: COMMENT; Schema: core_tables; Owner: postgres
--

COMMENT ON VIEW core_tables.vw_decade_genre_specialty IS 'Displays all decades, genres, and specialties side-by-side for reference or UI dropdowns.';


--
-- Name: vw_genre_list; Type: VIEW; Schema: core_tables; Owner: postgres
--

CREATE VIEW core_tables.vw_genre_list AS
 SELECT id AS genreid,
    genre_name AS name,
    display_name
   FROM core_tables.genre
  ORDER BY display_name;


ALTER VIEW core_tables.vw_genre_list OWNER TO postgres;

--
-- Name: vwspecialtylist; Type: VIEW; Schema: core_tables; Owner: postgres
--

CREATE VIEW core_tables.vwspecialtylist AS
 SELECT id AS specialtyid,
    specialty_name AS specialty
   FROM core_tables.specialty;


ALTER VIEW core_tables.vwspecialtylist OWNER TO postgres;

--
-- Name: artist_genre; Type: TABLE; Schema: join_tables; Owner: postgres
--

CREATE TABLE join_tables.artist_genre (
    id integer NOT NULL,
    artist_id integer,
    genre_id integer NOT NULL
);


ALTER TABLE join_tables.artist_genre OWNER TO postgres;

--
-- Name: TABLE artist_genre; Type: COMMENT; Schema: join_tables; Owner: postgres
--

COMMENT ON TABLE join_tables.artist_genre IS 'Links artists to the genres they are associated with. Each (artistid, genreid) pair is unique.';


--
-- Name: artistgenre_id_seq; Type: SEQUENCE; Schema: join_tables; Owner: postgres
--

CREATE SEQUENCE join_tables.artistgenre_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE join_tables.artistgenre_id_seq OWNER TO postgres;

--
-- Name: artistgenre_id_seq; Type: SEQUENCE OWNED BY; Schema: join_tables; Owner: postgres
--

ALTER SEQUENCE join_tables.artistgenre_id_seq OWNED BY join_tables.artist_genre.id;


--
-- Name: decade_genre; Type: TABLE; Schema: join_tables; Owner: postgres
--

CREATE TABLE join_tables.decade_genre (
    id integer NOT NULL,
    decade_id integer,
    genre_id integer
);


ALTER TABLE join_tables.decade_genre OWNER TO postgres;

--
-- Name: decadegenre_id_seq; Type: SEQUENCE; Schema: join_tables; Owner: postgres
--

CREATE SEQUENCE join_tables.decadegenre_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE join_tables.decadegenre_id_seq OWNER TO postgres;

--
-- Name: decadegenre_id_seq; Type: SEQUENCE OWNED BY; Schema: join_tables; Owner: postgres
--

ALTER SEQUENCE join_tables.decadegenre_id_seq OWNED BY join_tables.decade_genre.id;


--
-- Name: track_genre; Type: TABLE; Schema: join_tables; Owner: postgres
--

CREATE TABLE join_tables.track_genre (
    track_id integer NOT NULL,
    genre_id integer NOT NULL
);


ALTER TABLE join_tables.track_genre OWNER TO postgres;

--
-- Name: specialty_ranking; Type: TABLE; Schema: ranking_tables; Owner: postgres
--

CREATE TABLE ranking_tables.specialty_ranking (
    id integer NOT NULL,
    track_id integer,
    specialty_id integer,
    tracklist_id integer,
    ranking integer,
    intro text,
    detail text,
    artist_id integer,
    ranking_date date DEFAULT CURRENT_DATE,
    intro_mp3_url text
);


ALTER TABLE ranking_tables.specialty_ranking OWNER TO postgres;

--
-- Name: specialtyranking_id_seq; Type: SEQUENCE; Schema: ranking_tables; Owner: postgres
--

CREATE SEQUENCE ranking_tables.specialtyranking_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ranking_tables.specialtyranking_id_seq OWNER TO postgres;

--
-- Name: specialtyranking_id_seq; Type: SEQUENCE OWNED BY; Schema: ranking_tables; Owner: postgres
--

ALTER SEQUENCE ranking_tables.specialtyranking_id_seq OWNED BY ranking_tables.specialty_ranking.id;


--
-- Name: top40_genre_ranking; Type: TABLE; Schema: ranking_tables; Owner: postgres
--

CREATE TABLE ranking_tables.top40_genre_ranking (
    id integer NOT NULL,
    genre_id integer NOT NULL,
    artist_id integer NOT NULL,
    track_id integer NOT NULL,
    ranking integer NOT NULL,
    info text,
    detail text,
    ranking_date date DEFAULT CURRENT_DATE,
    intro_mp3_url text,
    CONSTRAINT check_rank_range CHECK (((ranking >= 1) AND (ranking <= 40)))
);


ALTER TABLE ranking_tables.top40_genre_ranking OWNER TO postgres;

--
-- Name: TABLE top40_genre_ranking; Type: COMMENT; Schema: ranking_tables; Owner: postgres
--

COMMENT ON TABLE ranking_tables.top40_genre_ranking IS 'Stores ranked artists within a genre, along with their top track. Each artist appears once per genre.';


--
-- Name: COLUMN top40_genre_ranking.genre_id; Type: COMMENT; Schema: ranking_tables; Owner: postgres
--

COMMENT ON COLUMN ranking_tables.top40_genre_ranking.genre_id IS 'Foreign key referencing genre(id). Defines the genre for the ranking.';


--
-- Name: COLUMN top40_genre_ranking.artist_id; Type: COMMENT; Schema: ranking_tables; Owner: postgres
--

COMMENT ON COLUMN ranking_tables.top40_genre_ranking.artist_id IS 'Foreign key referencing artist(id). The artist being ranked.';


--
-- Name: COLUMN top40_genre_ranking.track_id; Type: COMMENT; Schema: ranking_tables; Owner: postgres
--

COMMENT ON COLUMN ranking_tables.top40_genre_ranking.track_id IS 'Foreign key referencing track(id). The artist''s top track associated with the ranking.';


--
-- Name: COLUMN top40_genre_ranking.ranking; Type: COMMENT; Schema: ranking_tables; Owner: postgres
--

COMMENT ON COLUMN ranking_tables.top40_genre_ranking.ranking IS 'Ranking of the artist within the genre. Must be between 1 and 40.';


--
-- Name: topartistgenreranking_id_seq; Type: SEQUENCE; Schema: ranking_tables; Owner: postgres
--

CREATE SEQUENCE ranking_tables.topartistgenreranking_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ranking_tables.topartistgenreranking_id_seq OWNER TO postgres;

--
-- Name: topartistgenreranking_id_seq; Type: SEQUENCE OWNED BY; Schema: ranking_tables; Owner: postgres
--

ALTER SEQUENCE ranking_tables.topartistgenreranking_id_seq OWNED BY ranking_tables.top40_genre_ranking.id;


--
-- Name: track_ranking; Type: TABLE; Schema: ranking_tables; Owner: postgres
--

CREATE TABLE ranking_tables.track_ranking (
    id integer NOT NULL,
    track_id integer NOT NULL,
    decade_genre_id integer NOT NULL,
    tracklist_id integer DEFAULT 1 NOT NULL,
    ranking integer NOT NULL,
    intro text,
    ranking_date date DEFAULT CURRENT_DATE,
    CONSTRAINT check_ranking_range CHECK (((ranking >= 1) AND (ranking <= 70)))
);


ALTER TABLE ranking_tables.track_ranking OWNER TO postgres;

--
-- Name: track_ranking_id_seq; Type: SEQUENCE; Schema: ranking_tables; Owner: postgres
--

CREATE SEQUENCE ranking_tables.track_ranking_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ranking_tables.track_ranking_id_seq OWNER TO postgres;

--
-- Name: track_ranking_id_seq; Type: SEQUENCE OWNED BY; Schema: ranking_tables; Owner: postgres
--

ALTER SEQUENCE ranking_tables.track_ranking_id_seq OWNED BY ranking_tables.track_ranking.id;


--
-- Name: decade_genre_trivia; Type: TABLE; Schema: track_tables; Owner: postgres
--

CREATE TABLE track_tables.decade_genre_trivia (
    id integer NOT NULL,
    decade_genre_id integer NOT NULL,
    trivia text NOT NULL,
    trivia_mp3_url text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE track_tables.decade_genre_trivia OWNER TO postgres;

--
-- Name: decade_genre_trivia_id_seq; Type: SEQUENCE; Schema: track_tables; Owner: postgres
--

CREATE SEQUENCE track_tables.decade_genre_trivia_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE track_tables.decade_genre_trivia_id_seq OWNER TO postgres;

--
-- Name: decade_genre_trivia_id_seq; Type: SEQUENCE OWNED BY; Schema: track_tables; Owner: postgres
--

ALTER SEQUENCE track_tables.decade_genre_trivia_id_seq OWNED BY track_tables.decade_genre_trivia.id;


--
-- Name: track; Type: TABLE; Schema: track_tables; Owner: postgres
--

CREATE TABLE track_tables.track (
    id integer NOT NULL,
    track_name text NOT NULL,
    spotify_track_id text,
    album_name character varying(200),
    album_artwork text,
    year_released integer,
    is_explicit boolean DEFAULT false,
    duration_ms integer,
    popularity integer,
    artist_id integer NOT NULL,
    featured_artist_id integer,
    artist_display_name text,
    mode_flag text DEFAULT 0,
    detail text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE track_tables.track OWNER TO postgres;

--
-- Name: track_id_seq; Type: SEQUENCE; Schema: track_tables; Owner: postgres
--

CREATE SEQUENCE track_tables.track_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE track_tables.track_id_seq OWNER TO postgres;

--
-- Name: track_id_seq; Type: SEQUENCE OWNED BY; Schema: track_tables; Owner: postgres
--

ALTER SEQUENCE track_tables.track_id_seq OWNED BY track_tables.track.id;


--
-- Name: track_list; Type: TABLE; Schema: track_tables; Owner: postgres
--

CREATE TABLE track_tables.track_list (
    id integer NOT NULL,
    name text NOT NULL,
    curator text,
    is_official boolean DEFAULT false,
    language text DEFAULT 'English'::text,
    notes text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE track_tables.track_list OWNER TO postgres;

--
-- Name: tracklist_id_seq; Type: SEQUENCE; Schema: track_tables; Owner: postgres
--

CREATE SEQUENCE track_tables.tracklist_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE track_tables.tracklist_id_seq OWNER TO postgres;

--
-- Name: tracklist_id_seq; Type: SEQUENCE OWNED BY; Schema: track_tables; Owner: postgres
--

ALTER SEQUENCE track_tables.tracklist_id_seq OWNED BY track_tables.track_list.id;


--
-- Name: artist id; Type: DEFAULT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.artist ALTER COLUMN id SET DEFAULT nextval('core_tables.artist_id_seq'::regclass);


--
-- Name: decade id; Type: DEFAULT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.decade ALTER COLUMN id SET DEFAULT nextval('core_tables.decade_id_seq'::regclass);


--
-- Name: genre id; Type: DEFAULT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.genre ALTER COLUMN id SET DEFAULT nextval('core_tables.genre_id_seq'::regclass);


--
-- Name: specialty id; Type: DEFAULT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.specialty ALTER COLUMN id SET DEFAULT nextval('core_tables.specialty_id_seq'::regclass);


--
-- Name: artist_genre id; Type: DEFAULT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.artist_genre ALTER COLUMN id SET DEFAULT nextval('join_tables.artistgenre_id_seq'::regclass);


--
-- Name: decade_genre id; Type: DEFAULT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.decade_genre ALTER COLUMN id SET DEFAULT nextval('join_tables.decadegenre_id_seq'::regclass);


--
-- Name: specialty_ranking id; Type: DEFAULT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.specialty_ranking ALTER COLUMN id SET DEFAULT nextval('ranking_tables.specialtyranking_id_seq'::regclass);


--
-- Name: top40_genre_ranking id; Type: DEFAULT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.top40_genre_ranking ALTER COLUMN id SET DEFAULT nextval('ranking_tables.topartistgenreranking_id_seq'::regclass);


--
-- Name: track_ranking id; Type: DEFAULT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.track_ranking ALTER COLUMN id SET DEFAULT nextval('ranking_tables.track_ranking_id_seq'::regclass);


--
-- Name: decade_genre_trivia id; Type: DEFAULT; Schema: track_tables; Owner: postgres
--

ALTER TABLE ONLY track_tables.decade_genre_trivia ALTER COLUMN id SET DEFAULT nextval('track_tables.decade_genre_trivia_id_seq'::regclass);


--
-- Name: track id; Type: DEFAULT; Schema: track_tables; Owner: postgres
--

ALTER TABLE ONLY track_tables.track ALTER COLUMN id SET DEFAULT nextval('track_tables.track_id_seq'::regclass);


--
-- Name: track_list id; Type: DEFAULT; Schema: track_tables; Owner: postgres
--

ALTER TABLE ONLY track_tables.track_list ALTER COLUMN id SET DEFAULT nextval('track_tables.tracklist_id_seq'::regclass);


--
-- Name: artist artist_name_key; Type: CONSTRAINT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.artist
    ADD CONSTRAINT artist_name_key UNIQUE (artist_name);


--
-- Name: artist artist_pkey; Type: CONSTRAINT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.artist
    ADD CONSTRAINT artist_pkey PRIMARY KEY (id);


--
-- Name: artist artist_spotify_artist_id_key; Type: CONSTRAINT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.artist
    ADD CONSTRAINT artist_spotify_artist_id_key UNIQUE (spotify_artist_id);


--
-- Name: decade decade_name_key; Type: CONSTRAINT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.decade
    ADD CONSTRAINT decade_name_key UNIQUE (decade_name);


--
-- Name: decade decade_pkey; Type: CONSTRAINT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.decade
    ADD CONSTRAINT decade_pkey PRIMARY KEY (id);


--
-- Name: genre genre_genre_name_key; Type: CONSTRAINT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.genre
    ADD CONSTRAINT genre_genre_name_key UNIQUE (genre_name);


--
-- Name: genre genre_name_key; Type: CONSTRAINT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.genre
    ADD CONSTRAINT genre_name_key UNIQUE (genre_name);


--
-- Name: genre genre_pkey; Type: CONSTRAINT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.genre
    ADD CONSTRAINT genre_pkey PRIMARY KEY (id);


--
-- Name: language language_pkey; Type: CONSTRAINT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.language
    ADD CONSTRAINT language_pkey PRIMARY KEY (code);


--
-- Name: specialty specialty_pkey; Type: CONSTRAINT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.specialty
    ADD CONSTRAINT specialty_pkey PRIMARY KEY (id);


--
-- Name: specialty specialty_specialty_name_key; Type: CONSTRAINT; Schema: core_tables; Owner: postgres
--

ALTER TABLE ONLY core_tables.specialty
    ADD CONSTRAINT specialty_specialty_name_key UNIQUE (specialty_name);


--
-- Name: artist_genre artistgenre_artistid_genreid_key; Type: CONSTRAINT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.artist_genre
    ADD CONSTRAINT artistgenre_artistid_genreid_key UNIQUE (artist_id, genre_id);


--
-- Name: artist_genre artistgenre_pkey; Type: CONSTRAINT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.artist_genre
    ADD CONSTRAINT artistgenre_pkey PRIMARY KEY (id);


--
-- Name: decade_genre decadegenre_decade_id_genre_id_key; Type: CONSTRAINT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.decade_genre
    ADD CONSTRAINT decadegenre_decade_id_genre_id_key UNIQUE (decade_id, genre_id);


--
-- Name: decade_genre decadegenre_pkey; Type: CONSTRAINT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.decade_genre
    ADD CONSTRAINT decadegenre_pkey PRIMARY KEY (id);


--
-- Name: track_genre trackgenre_pkey; Type: CONSTRAINT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.track_genre
    ADD CONSTRAINT trackgenre_pkey PRIMARY KEY (track_id, genre_id);


--
-- Name: specialty_ranking specialty_ranking_pkey; Type: CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.specialty_ranking
    ADD CONSTRAINT specialty_ranking_pkey PRIMARY KEY (id);


--
-- Name: specialty_ranking specialty_ranking_track_id_specialty_id_tracklist_id_key; Type: CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.specialty_ranking
    ADD CONSTRAINT specialty_ranking_track_id_specialty_id_tracklist_id_key UNIQUE (track_id, specialty_id, tracklist_id);


--
-- Name: top40_genre_ranking topartistgenreranking_pkey; Type: CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.top40_genre_ranking
    ADD CONSTRAINT topartistgenreranking_pkey PRIMARY KEY (id);


--
-- Name: track_ranking track_ranking_track_id_decade_genre_id_tracklist_id_key; Type: CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.track_ranking
    ADD CONSTRAINT track_ranking_track_id_decade_genre_id_tracklist_id_key UNIQUE (track_id, decade_genre_id, tracklist_id);


--
-- Name: track_ranking trackranking_pkey; Type: CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.track_ranking
    ADD CONSTRAINT trackranking_pkey PRIMARY KEY (id);


--
-- Name: track_ranking uix_rank_per_decade_genre; Type: CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.track_ranking
    ADD CONSTRAINT uix_rank_per_decade_genre UNIQUE (ranking, decade_genre_id);


--
-- Name: top40_genre_ranking unique_artist_per_genre; Type: CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.top40_genre_ranking
    ADD CONSTRAINT unique_artist_per_genre UNIQUE (genre_id, artist_id);


--
-- Name: top40_genre_ranking unique_ranking_per_genre; Type: CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.top40_genre_ranking
    ADD CONSTRAINT unique_ranking_per_genre UNIQUE (genre_id, ranking);


--
-- Name: specialty_ranking unique_ranking_per_specialty; Type: CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.specialty_ranking
    ADD CONSTRAINT unique_ranking_per_specialty UNIQUE (specialty_id, ranking);


--
-- Name: decade_genre_trivia decade_genre_trivia_pkey; Type: CONSTRAINT; Schema: track_tables; Owner: postgres
--

ALTER TABLE ONLY track_tables.decade_genre_trivia
    ADD CONSTRAINT decade_genre_trivia_pkey PRIMARY KEY (id);


--
-- Name: track track_pkey; Type: CONSTRAINT; Schema: track_tables; Owner: postgres
--

ALTER TABLE ONLY track_tables.track
    ADD CONSTRAINT track_pkey PRIMARY KEY (id);


--
-- Name: track track_spotify_track_id_key; Type: CONSTRAINT; Schema: track_tables; Owner: postgres
--

ALTER TABLE ONLY track_tables.track
    ADD CONSTRAINT track_spotify_track_id_key UNIQUE (spotify_track_id);


--
-- Name: track_list tracklist_pkey; Type: CONSTRAINT; Schema: track_tables; Owner: postgres
--

ALTER TABLE ONLY track_tables.track_list
    ADD CONSTRAINT tracklist_pkey PRIMARY KEY (id);


--
-- Name: unique_genre_name_lower; Type: INDEX; Schema: core_tables; Owner: postgres
--

CREATE UNIQUE INDEX unique_genre_name_lower ON core_tables.genre USING btree (lower(genre_name));


--
-- Name: uq_spotify_artist_id_partial; Type: INDEX; Schema: core_tables; Owner: postgres
--

CREATE UNIQUE INDEX uq_spotify_artist_id_partial ON core_tables.artist USING btree (spotify_artist_id) WHERE (spotify_artist_id IS NOT NULL);


--
-- Name: artist_genre artistgenre_artistid_fkey; Type: FK CONSTRAINT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.artist_genre
    ADD CONSTRAINT artistgenre_artistid_fkey FOREIGN KEY (artist_id) REFERENCES core_tables.artist(id);


--
-- Name: artist_genre artistgenre_genreid_fkey; Type: FK CONSTRAINT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.artist_genre
    ADD CONSTRAINT artistgenre_genreid_fkey FOREIGN KEY (genre_id) REFERENCES core_tables.genre(id);


--
-- Name: decade_genre decadegenre_decade_id_fkey; Type: FK CONSTRAINT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.decade_genre
    ADD CONSTRAINT decadegenre_decade_id_fkey FOREIGN KEY (decade_id) REFERENCES core_tables.decade(id);


--
-- Name: decade_genre decadegenre_genre_id_fkey; Type: FK CONSTRAINT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.decade_genre
    ADD CONSTRAINT decadegenre_genre_id_fkey FOREIGN KEY (genre_id) REFERENCES core_tables.genre(id);


--
-- Name: artist_genre fk_artistgenre_genre_id; Type: FK CONSTRAINT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.artist_genre
    ADD CONSTRAINT fk_artistgenre_genre_id FOREIGN KEY (genre_id) REFERENCES core_tables.genre(id) ON DELETE CASCADE;


--
-- Name: track_genre trackgenre_genre_id_fkey; Type: FK CONSTRAINT; Schema: join_tables; Owner: postgres
--

ALTER TABLE ONLY join_tables.track_genre
    ADD CONSTRAINT trackgenre_genre_id_fkey FOREIGN KEY (genre_id) REFERENCES core_tables.genre(id) ON DELETE CASCADE;


--
-- Name: top40_genre_ranking fk_topartistgenre_artist; Type: FK CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.top40_genre_ranking
    ADD CONSTRAINT fk_topartistgenre_artist FOREIGN KEY (artist_id) REFERENCES core_tables.artist(id) ON DELETE CASCADE;


--
-- Name: top40_genre_ranking fk_topartistgenre_genre; Type: FK CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.top40_genre_ranking
    ADD CONSTRAINT fk_topartistgenre_genre FOREIGN KEY (genre_id) REFERENCES core_tables.genre(id) ON DELETE CASCADE;


--
-- Name: specialty_ranking specialty_ranking_specialty_id_fkey; Type: FK CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.specialty_ranking
    ADD CONSTRAINT specialty_ranking_specialty_id_fkey FOREIGN KEY (specialty_id) REFERENCES core_tables.specialty(id);


--
-- Name: specialty_ranking specialty_ranking_tracklist_id_fkey; Type: FK CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.specialty_ranking
    ADD CONSTRAINT specialty_ranking_tracklist_id_fkey FOREIGN KEY (tracklist_id) REFERENCES track_tables.track_list(id);


--
-- Name: track_ranking track_ranking_tracklist_id_fkey; Type: FK CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.track_ranking
    ADD CONSTRAINT track_ranking_tracklist_id_fkey FOREIGN KEY (tracklist_id) REFERENCES track_tables.track_list(id);


--
-- Name: track_ranking trackranking_decadegenreid_fkey; Type: FK CONSTRAINT; Schema: ranking_tables; Owner: postgres
--

ALTER TABLE ONLY ranking_tables.track_ranking
    ADD CONSTRAINT trackranking_decadegenreid_fkey FOREIGN KEY (decade_genre_id) REFERENCES join_tables.decade_genre(id);


--
-- Name: decade_genre_trivia decade_genre_trivia_decade_genre_id_fkey; Type: FK CONSTRAINT; Schema: track_tables; Owner: postgres
--

ALTER TABLE ONLY track_tables.decade_genre_trivia
    ADD CONSTRAINT decade_genre_trivia_decade_genre_id_fkey FOREIGN KEY (decade_genre_id) REFERENCES join_tables.decade_genre(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

