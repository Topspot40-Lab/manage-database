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
-- Data for Name: artist; Type: TABLE DATA; Schema: core_tables; Owner: postgres
--

COPY core_tables.artist (id, artist_name, spotify_artist_id, artist_artwork, artist_description, not_on_spotify) FROM stdin;
1	florida georgia line	3b8QkneNDz4JHKKKlLgYZg	https://i.scdn.co/image/ab6761610000e5ebaa2d9bd207a62adc3edf6631	Florida Georgia Line, a duo consisting of Tyler Hubbard and Brian Kelley, has been a major force in the country music scene since their breakout hit 'Cruise' in 2012. They are known for blending country with elements of pop, rock, and hip-hop, which has helped them achieve widespread commercial success and influence the genre's evolution. Their accolades include multiple Academy of Country Music Awards and a Grammy nomination, reflecting their significant impact on modern country music.	f
2	thomas rhett	6x2LnllRG5uGarZMsD4iO8	https://i.scdn.co/image/ab6761610000e5eb7538436ea7437322f6f389ca	Thomas Rhett has quickly risen to prominence in country music with his infectious blend of country, pop, and R&B influences. Since his debut album in 2013, he has released numerous chart-topping hits like 'Die a Happy Man' and 'Marry Me', showcasing his versatility and songwriting prowess. Rhett's energetic performances and relatable lyrics have earned him multiple awards, including the Academy of Country Music's Male Vocalist of the Year.	f
3	lee ann womack	738OS3zrCO782uDiUN9pet	https://i.scdn.co/image/ab6761610000e5eb86a12d477e7e1cb4e4b26caa	Lee Ann Womack is a prominent figure in country music, known for her traditional style and emotive vocals. Her breakthrough hit 'I Hope You Dance' won multiple awards, including a Grammy for Best Country Song, and became an anthem for hope and inspiration. Womack's dedication to preserving the roots of country music has earned her respect and admiration within the industry.	f
4	alan jackson	4mxWe1mtYIYfP040G38yvS	https://i.scdn.co/image/ab6772690000c46c1dce50b93ca0b1e2f459d9e6	Alan Jackson is a cornerstone of country music, celebrated for his neotraditionalist style that harks back to the genre's roots. With hits like 'Chattahoochee' and 'Remember When,' he has won numerous awards, including multiple Grammys and CMA Awards. Jackson's influence extends beyond music, as he has been inducted into the Country Music Hall of Fame.	f
5	lonestar	3qbnxnvUqR14MJ9g8QwZJK	https://i.scdn.co/image/ab6761610000e5eb1bc8cec709c2452275e53050	Lonestar is a country music band known for their harmonious sound and crossover success. Their hit 'Amazed' topped both the country and pop charts, showcasing their versatility. The band's enduring popularity is evident in their continued touring and the impact of their music on fans across generations.	f
6	toby keith	2bA6fzP0lMAQ4kz6CF61w8	https://i.scdn.co/image/ab6761610000e5eb1b6b9d83cfd806b328496207	Toby Keith is known for his bold, patriotic songs and his significant impact on country music. Hits like 'Courtesy of the Red, White and Blue' and 'Red Solo Cup' have become cultural touchstones. Keith's entrepreneurial spirit is also notable, as he founded his own record label, Show Dog Nashville.	f
7	jimmy buffett	28AyklUmMECPwdfo8NEsV0	https://i.scdn.co/image/ab6761610000e5ebc51b2d9deea2b3cc8360828d	Jimmy Buffett is synonymous with the laid-back, tropical lifestyle he celebrates in his music. His song 'Margaritaville' became a cultural phenomenon and led to a successful business empire. Buffett's influence extends beyond music, as he has authored books and created a brand that embodies his carefree ethos.	f
8	gretchen wilson	0IdYRFTswLdsGwSnzOaGNF	https://i.scdn.co/image/ab6761610000e5ebcfcc10b18f534f720a976dc3	Gretchen Wilson burst onto the country scene with her hit 'Redneck Woman,' which celebrated blue-collar pride and authenticity. Her debut album, 'Here for the Party,' won her a Grammy for Best Female Country Vocal Performance. Wilson's raw, unapologetic style has made her a beloved figure in country music.	f
9	big and rich	0oBEeN6BCxEgMogzThqrPf	https://i.scdn.co/image/ab6761610000e5ebc8c403161c81d8f8c02c0506	Big & Rich, comprised of Big Kenny and John Rich, are known for their eclectic blend of country, rock, and hip-hop. Their hit 'Save a Horse (Ride a Cowboy)' became an anthem for their unique style. The duo's influence extends to their founding of the MuzikMafia, a collective that fosters musical collaboration and innovation.	f
10	sara evans	7qvsLYsYP0MHD7jkdv6DAG	https://i.scdn.co/image/ab6761610000e5ebda10d709fefcb48fbdad45ad	Sara Evans is celebrated for her powerful vocals and heartfelt lyrics. Hits like 'Born to Fly' and 'Suds in the Bucket' showcase her ability to connect with audiences. Evans has been recognized with multiple awards, including the Academy of Country Music's Top Female Vocalist.	f
11	kenny chesney	3grHWM9bx2E9vwJCdlRv9O	https://i.scdn.co/image/ab6761610000e5eb5de44c9558a47909debca2cd	Kenny Chesney is known for his tropical-themed songs and energetic live performances. Hits like 'No Shoes, No Shirt, No Problems' and 'When the Sun Goes Down' have defined his career. Chesney's influence extends to his philanthropy, particularly through his work with the Love for Love City Foundation.	f
12	uncle kracker	2DnqqkzzDKm3vAoyHtn8So	https://i.scdn.co/image/ab6761610000e5ebae45d8ab89ad4aff41dfb021	Uncle Kracker, born Matthew Shafer, is known for his blend of rock, country, and hip-hop. His hit 'Follow Me' crossed genres and showcased his versatility. Kracker's collaboration with Kenny Chesney on 'When the Sun Goes Down' further solidified his place in country music.	f
13	tim mcgraw	6roFdX1y5BYSbp60OTJWMd	https://i.scdn.co/image/ab6761610000e5ebbd6977f3970a7a4a8d4becbe	Tim McGraw is a country music icon known for his soulful voice and storytelling ability. Hits like 'Live Like You Were Dying' and 'Humble and Kind' have resonated with audiences worldwide. McGraw's influence extends to his acting career and his advocacy for various social causes.	f
14	willie nelson	5W5bDNCqJ1jbCgTxDD0Cb3	https://i.scdn.co/image/ab6772690000c46c82a531f8f5067e13517f5b15	Willie Nelson is a legendary figure in country music, known for his distinctive voice and songwriting. Hits like 'On the Road Again' and 'Always on My Mind' have become classics. Nelson's impact extends beyond music, as he is also recognized for his activism and philanthropy.	f
15	rascal flatts	0a1gHP0HAqALbEyxaD5Ngn	https://i.scdn.co/image/ab6761610000e5eb6772748e5cd3c3de721f8c03	Rascal Flatts is a country music trio known for their harmonious vocals and crossover success. Hits like 'Bless the Broken Road' and 'Life is a Highway' have become anthems. The group's influence is evident in their numerous awards, including multiple ACM and CMA Awards.	f
16	keith urban	0u2FHSq3ln94y5Q57xazwf	https://i.scdn.co/image/ab6761610000e5eb054c067d4cfa3b8094f3400f	Keith Urban is known for his fusion of country and rock music, as well as his virtuoso guitar skills. Hits like 'Somebody Like You' and 'Blue Ain't Your Color' have showcased his versatility. Urban's influence extends to his work as a judge on 'American Idol' and his advocacy for mental health.	f
17	brandon lake	1bdnGJxkbIIys5Jhk1T74v	https://i.scdn.co/image/ab6761610000e5eb8ba23cfe3ff56cc69b68f10e	Brandon Lake is a contemporary Christian music artist known for his worship songs. His collaboration on 'Gratitude' with Elevation Worship has resonated with audiences worldwide. Lake's influence extends to his work as a songwriter and his commitment to spreading faith through music.	f
18	brad paisley	13YmWQJFwgZrd4bf5IjMY4	https://i.scdn.co/image/ab6761610000e5eb49b3eca30283993e5794c6ef	Brad Paisley is known for his skillful guitar playing and witty songwriting. Hits like 'Whiskey Lullaby' and 'Remind Me' have showcased his storytelling ability. Paisley's influence extends to his philanthropy, particularly through his work with the Country Music Hall of Fame and Museum.	f
19	alison krauss	5J6L7N6B4nI1M5cwa29mQG	https://i.scdn.co/image/ab6761610000e5eb9870f6d61fa488a37fcb58df	Alison Krauss is a bluegrass and country music artist known for her angelic voice and virtuoso fiddle playing. Her collaborations with Robert Plant on 'Raising Sand' earned her multiple Grammys. Krauss's influence extends to her work as a producer and her dedication to preserving traditional music.	f
20	carrie underwood	4xFUf1FHVy696Q1JQZMTRj	https://i.scdn.co/image/ab6761610000e5eb69084d0b776e725025329043	Carrie Underwood rose to fame as the winner of 'American Idol' and has since become a powerhouse in country music. Hits like 'Before He Cheats' and 'Jesus, Take the Wheel' have showcased her vocal prowess. Underwood's influence extends to her philanthropy, particularly through her work with the C.A.T.S. Foundation.	f
21	beyonce	6vWDO969PvNqNYHIOW5v0m	https://i.scdn.co/image/ab6761610000e5eb7eaa373538359164b843f7c0	Beyoncé is a global icon known for her powerful vocals and dynamic performances. She rose to fame as a member of Destiny's Child before launching a successful solo career. Her album 'Lemonade' was critically acclaimed for its thematic depth and visual storytelling, earning her numerous Grammy Awards.	f
22	jayz	3nFkdlSjzX9mRTtwJOzDYB	https://i.scdn.co/image/ab6761610000e5eb3fdebba252a8c568d3c0f7aa	Jay-Z, born Shawn Carter, is a legendary rapper and entrepreneur who has significantly influenced hip-hop culture. He co-founded Roc-A-Fella Records and later became the president of Def Jam Recordings. His business acumen extends to fashion with the creation of Rocawear and sports management with Roc Nation.	f
23	kelly clarkson	3BmGtnKgCSGYIUhmivXKWX	https://i.scdn.co/image/ab6761610000e5eb20b8c7d395994dc81a85f291	Kelly Clarkson became the first winner of 'American Idol' and has since established herself as a versatile artist. Her powerful voice and emotional depth are showcased in hits like 'Since U Been Gone' and 'Stronger (What Doesn't Kill You).' She has won multiple Grammy Awards and is known for her candid personality.	f
24	outkast	1G9G7WwrXka3Z1r7aIDjI7	https://i.scdn.co/image/ab6761610000e5eb0cb3f95b9f8f7337e135a925	OutKast, comprised of André 3000 and Big Boi, revolutionized Southern hip-hop with their innovative sound and eclectic style. Their album 'Speakerboxxx/The Love Below' won the Grammy for Album of the Year, a rare feat for a hip-hop album. They are celebrated for blending genres and pushing creative boundaries.	f
25	kanye west	5K4W6rqBFWDnAN6FQUkS6x	https://i.scdn.co/image/ab6761610000e5eb6e835a500e791bf9c27a422a	Kanye West is a polarizing figure known for his groundbreaking music and outspoken personality. From his debut 'The College Dropout' to 'My Beautiful Dark Twisted Fantasy,' he has consistently pushed the boundaries of hip-hop and pop. His fashion ventures and public persona have also made significant cultural impacts.	f
26	jamie foxx	7LnaAXbDVIL75IVPnndf7w	https://i.scdn.co/image/a3823abbd476fa00cdf95a9f5cbbe09d2f96add2	Jamie Foxx is a multi-talented artist known for his work in music, film, and television. He won an Academy Award for Best Actor for his portrayal of Ray Charles in 'Ray.' His music career includes hits like 'Blame It' and collaborations with other artists across genres.	f
27	usher	23zg3TcAtWQy7J6upgbUnj	https://i.scdn.co/image/ab6761610000e5eb716114797a4a644c67c5fa72	Usher is a prominent R&B artist known for his smooth vocals and dynamic dance moves. His album 'Confessions' is one of the best-selling albums of the 2000s, featuring hits like 'Yeah!' and 'Burn.' He has won numerous awards, including eight Grammy Awards.	f
28	lil jon	7sfl4Xt5KmfyDs2T3SVSMK	https://i.scdn.co/image/ab6761610000e5ebf893feb44e74c8b4c15ecc95	Lil Jon is a key figure in the crunk music scene, known for his energetic style and catchy hooks. He gained widespread fame with hits like 'Get Low' and 'Turn Down for What.' His influence extends to popularizing the term 'crunk' and his work as a producer.	f
29	black eyed peas	1yxSLGMDHlW21z4YXirZDS	https://i.scdn.co/image/ab6761610000e5ebb3037310c07b99cbefbd2c6d	The Black Eyed Peas are a versatile group known for blending hip-hop, pop, and electronic music. Their album 'The E.N.D.' produced global hits like 'I Gotta Feeling' and 'Boom Boom Pow.' They have won six Grammy Awards and are recognized for their energetic live performances.	f
30	lady gaga	1HY2Jd0NmPuamShAr6KMms	https://i.scdn.co/image/ab6761610000e5ebaadc18cac8d48124357c38e6	Lady Gaga is known for her bold fashion choices and powerful vocals. She rose to fame with her debut album 'The Fame,' featuring hits like 'Just Dance' and 'Poker Face.' Her advocacy for the LGBTQ+ community and her philanthropy work have also made significant cultural impacts.	f
31	rihanna	5pKCCKE2ajJHZ9KAiaK11H	https://i.scdn.co/image/ab6761610000e5eb373e1be0410d4212bf72acab	Rihanna is a Barbadian singer and businesswoman known for her versatile music and fashion ventures. Her albums 'Good Girl Gone Bad' and 'Anti' have produced numerous hits, including 'Umbrella' and 'Work.' She has also founded successful brands like Fenty Beauty and Savage X Fenty.	f
32	gwen stefani	4yiQZ8tQPux8cPriYMWUFP	https://i.scdn.co/image/ab6761610000e5eb64b94bebbaee56f793e24853	Gwen Stefani first gained fame as the lead singer of No Doubt before launching a successful solo career. Her album 'Love. Angel. Music. Baby.' featured hits like 'Hollaback Girl' and 'Rich Girl.' She is also known for her fashion line L.A.M.B. and her work as a coach on 'The Voice.'	f
33	britney spears	26dSoYclwsYLMAKD3tpOr4	https://i.scdn.co/image/ab6761610000e5eb26e59b825251b7df20a7b65e	Britney Spears is a pop icon known for her catchy songs and iconic performances. Her debut album '...Baby One More Time' launched her to stardom, and she has since released numerous hits like 'Toxic' and 'Oops!... I Did It Again.' Her influence on pop culture and music is undeniable.	f
34	flo rida	0jnsk9HBra6NMjO2oANoPY	https://i.scdn.co/image/ab6761610000e5eb655ca8f3196953554b479452	Flo Rida is known for his infectious club anthems and collaborations with various artists. His hits include 'Low,' 'Right Round,' and 'Club Can't Handle Me.' He has a knack for blending hip-hop and pop, making him a staple in the music industry.	f
35	tpain	3aQeKQSyrW4qWr35idm0cy	https://i.scdn.co/image/ab6761610000e5ebeac6cf38775b541255dc13a6	T-Pain is famous for popularizing the use of Auto-Tune in his music. His hits include 'Buy U a Drank (Shawty Snappin')' and 'Bartender.' He has won two Grammy Awards and is known for his unique vocal style and production work.	f
36	leona lewis	5lKZWd6HiSCLfnDGrq9RAm	https://i.scdn.co/image/ab6761610000e5ebe9cf3862b8027eb5b9f6b831	Leona Lewis rose to fame after winning 'The X Factor' in the UK. Her debut album 'Spirit' featured the hit 'Bleeding Love,' which became an international success. She is known for her powerful vocals and has since released several successful albums.	f
37	50 cent	3q7HBObVc0L8jNeTe5Gofh	https://i.scdn.co/image/dd031b9c5d1b6eba4a691cd89c954255aae787f2	50 Cent, born Curtis Jackson, is known for his gritty lyrics and entrepreneurial spirit. His debut album 'Get Rich or Die Tryin'' was a massive success, featuring hits like 'In da Club.' He has also ventured into acting and founded the successful liquor brand, Sire Spirits.	f
38	olivia	5YBSzuCs7WaFKNr7Bky0Uf	https://i.scdn.co/image/ab6761610000e5ebe03a98785f3658f0b6461ec4	Olivia is an R&B singer who gained fame with her hit 'Bizounce.' She was signed to J Records and later collaborated with 50 Cent on 'Candy Shop.' Her powerful voice and stage presence have made her a notable figure in the music industry.	f
39	colby odonis	7fObcBw9VM3x7ntWKCYl0z	https://i.scdn.co/image/ab6761610000e5eb2c44e078944196a8c1eec256	Colby O'Donis is known for his collaborations with other artists, including Lady Gaga on 'Just Dance.' His smooth vocals and R&B style have earned him a place in the music industry. He has also released solo work, showcasing his versatility.	f
40	lil wayne	55Aa2cqylxrFIXC767Z865	https://i.scdn.co/image/ab6761610000e5eb998010cd1075921b5faf16b2	Lil Wayne, born Dwayne Carter Jr., is a prolific rapper known for his mixtape series and albums like 'Tha Carter III.' He has won multiple Grammy Awards and is celebrated for his unique flow and lyrical prowess. His influence on hip-hop is extensive.	f
41	static major	3pbi8H08p95NUZ7m6ybxUV	https://i.scdn.co/image/ab6761610000e5eb5ccc476e8b18673e01d87420	Static Major, born Stephen Garrett, was a talented singer and songwriter known for his work with Aaliyah and Ginuwine. He co-wrote the hit 'Lollipop' for Lil Wayne, which became a posthumous success after his untimely death. His contributions to R&B and hip-hop are significant.	f
42	nelly	2gBjLmx6zQnFGQJCAQpRgw	https://i.scdn.co/image/3677690af58abb70a5c5fd58d69db4d1ad705d4f	Nelly is known for his unique rap style and catchy hooks. His debut album 'Country Grammar' featured the hit 'Ride wit Me,' and he has since released numerous successful albums. He is also recognized for his philanthropy work and business ventures.	f
43	sean paul	3Isy6kedDrgPYoTS1dazA9	https://i.scdn.co/image/ab6761610000e5eb60c3e9abe7327c0097738f22	Sean Paul is a Jamaican dancehall artist known for his distinctive voice and infectious rhythms. His hits include 'Temperature' and 'Get Busy,' which have crossed over into mainstream pop. He has won a Grammy Award and is a major figure in the dancehall genre.	f
44	katy perry	6jJ0s89eD6GaHleKKya26X	https://i.scdn.co/image/ab6761610000e5eb0988562f78810e47a6e3325f	Katy Perry is known for her colorful pop music and theatrical performances. Her album 'Teenage Dream' produced multiple number-one hits, including 'Firework' and 'California Gurls.' She is also recognized for her advocacy work and her role as a judge on 'American Idol.'	f
45	kesha	6LqNN22kT3074XbTVUrhzX	https://i.scdn.co/image/ab6761610000e5eb1c43cbfb50d7ac393df96ae5	Kesha is known for her party anthems and unique vocal style. Her debut album 'Animal' featured hits like 'Tik Tok' and 'Your Love Is My Drug.' She has since released more personal and introspective work, showcasing her versatility as an artist.	f
46	taio cruz	6MF9fzBmfXghAz953czmBC	https://i.scdn.co/image/ab6761610000e5eb153171480a6f22912253b9f1	Taio Cruz is a British singer-songwriter known for his pop and R&B hits. His songs 'Break Your Heart' and 'Dynamite' became international successes. He is also recognized for his work as a producer and songwriter for other artists.	f
47	taylor swift	06HL4z0CvFAxyc27GXpf02	https://i.scdn.co/image/ab6761610000e5ebe672b5f553298dcdccb0e676	Taylor Swift is known for her narrative songwriting and genre versatility. She began her career in country music before transitioning to pop with albums like '1989' and 'Reputation.' Her influence extends to her advocacy for artists' rights and her philanthropy work.	f
48	alicia keys	3DiDSECUqqY1AuBP8qtaIa	https://i.scdn.co/image/ab6761610000e5ebebfd16a3bca87c31c1e20576	Alicia Keys is known for her soulful voice and piano skills. Her debut album 'Songs in A Minor' featured the hit 'Fallin',' and she has since released numerous successful albums. She is also recognized for her advocacy work and her role as a judge on 'The Voice.'	f
49	shakira	0EmeFodog0BfCgMzAIvKQp	https://i.scdn.co/image/ab6761610000e5eb2528c726e5ddb90a7197e527	Shakira is a Colombian singer known for her unique voice and dance moves. Her hits include 'Hips Don't Lie' and 'Whenever, Wherever.' She is also recognized for her philanthropy work, particularly through her Pies Descalzos Foundation.	f
50	wyclef jean	7aBzpmFXB4WWpPl2F7RjBe	https://i.scdn.co/image/ab6761610000e5ebad53e714cc3481bd069bfc93	Wyclef Jean is a Haitian-American musician known for his work with the Fugees and his solo career. His hits include 'Gone Till November' and 'Sweetest Girl (Dollar Bill).' He is also recognized for his philanthropy work and his political activism.	f
51	justin timberlake	31TPClRtHm23RisEBtV3X7	https://i.scdn.co/image/ab6761610000e5eb7a5cfe2597665a3d160e805e	Justin Timberlake is known for his smooth vocals and dynamic performances. He rose to fame with NSYNC before launching a successful solo career. His albums 'Justified' and 'FutureSex/LoveSounds' produced hits like 'Cry Me a River' and 'SexyBack.'	f
52	timbaland	5Y5TRrQiqgUO4S36tzjIRZ	https://i.scdn.co/image/ab6761610000e5ebb713079a55dcf937d241dd2b	Timbaland is a renowned producer and rapper known for his innovative beats and collaborations. He has worked with artists like Aaliyah, Missy Elliott, and Justin Timberlake. His production style has significantly influenced the sound of modern pop and hip-hop.	f
53	nelly furtado	2jw70GZXlAI8QzWeY2bgRc	https://i.scdn.co/image/ab6761610000e5ebd2ce0bf5614b54bd44e059d5	Nelly Furtado is known for her versatile music style, blending pop, folk, and hip-hop. Her album 'Loose' featured hits like 'Promiscuous' and 'Maneater.' She is also recognized for her multilingual abilities and her advocacy for social issues.	f
54	avril lavigne	0p4nmQO2msCgU4IF37Wi3j	https://i.scdn.co/image/ab6761610000e5ebcea575e8c9519d4367984256	Avril Lavigne is known for her punk-influenced pop music and rebellious image. Her debut album 'Let Go' featured hits like 'Complicated' and 'Sk8er Boi.' She has since released several successful albums and is recognized for her songwriting skills.	f
55	mary j blige	1XkoF8ryArs86LZvFOkbyr	https://i.scdn.co/image/ab6761610000e5eb3d7888ba4d2bf67fe6b64a55	Mary J. Blige is known as the 'Queen of Hip-Hop Soul' for her fusion of R&B and hip-hop. Her album 'My Life' is considered a classic, and she has won numerous Grammy Awards. Her powerful vocals and emotional depth have made her a legendary figure in music.	f
56	snoop dogg	7hJcb9fa4alzcOq3EaNPoG	https://i.scdn.co/image/ab6761610000e5ebc19a88576ebe6fcbb325c297	Snoop Dogg, born Calvin Broadus Jr., is a legendary rapper known for his laid-back style and distinctive voice. His debut album 'Doggystyle' was a massive success, and he has since released numerous albums and collaborated with various artists. He is also recognized for his ventures into acting and business.	f
57	pharrell williams	2RdwBSPQiwcmiDo9kixcl8	https://i.scdn.co/image/ab6761610000e5ebf0789cd783c20985ec3deb4e	Pharrell Williams is a multi-talented artist known for his work as a singer, producer, and fashion designer. His hits include 'Happy' and 'Blurred Lines,' and he has won multiple Grammy Awards. His production work with The Neptunes has significantly influenced modern music.	f
58	eminem	7dGJo4pcD2V6oG8kP0tJRR	https://i.scdn.co/image/ab6761610000e5eba00b11c129b27a88fc72f36b	Eminem, born Marshall Mathers, is known for his rapid-fire delivery and controversial lyrics. His albums 'The Marshall Mathers LP' and 'The Eminem Show' are considered classics, and he has won numerous Grammy Awards. His influence on hip-hop and pop culture is undeniable.	f
59	coldplay	4gzpq5DPGxSnKTe4SA8HAU	https://i.scdn.co/image/ab6761610000e5eb1ba8fc5f5c73e7e9313cc6eb	Coldplay is known for their anthemic rock sound and introspective lyrics. Their album 'A Rush of Blood to the Head' featured hits like 'Clocks' and 'The Scientist.' They have won multiple Grammy Awards and are recognized for their live performances and philanthropy work.	f
60	snow patrol	3rIZMv9rysU7JkLzEaC5Jp	https://i.scdn.co/image/ab6761610000e5eb9b328846dc38b0a620da1ce2	Snow Patrol is known for their emotive rock music and heartfelt lyrics. Their album 'Eyes Open' featured the hit 'Chasing Cars,' which became a global success. They have won multiple awards and are recognized for their live performances and songwriting.	f
61	the fray	0zOcE3mg9nS6l3yxt1Y0bK	https://i.scdn.co/image/ab6761610000e5ebfbde447822e329707f1c4ea3	The Fray is known for their piano-driven rock sound and emotional lyrics. Their debut album featured the hit 'How to Save a Life,' which became a cultural phenomenon. They have won multiple awards and are recognized for their live performances and songwriting.	f
62	nickelback	6deZN1bslXzeGvOLaLMOIF	https://i.scdn.co/image/ab6761610000e5eb4ad382f899596d8c7b9e8e09	Nickelback, formed in 1995, is a Canadian rock band known for their mainstream success with hits like 'How You Remind Me' and 'Photograph.' Despite being one of the best-selling acts of the 2000s, they have faced significant criticism and internet memes, which has become a part of their cultural legacy. Their music often blends hard rock with post-grunge elements, appealing to a broad audience.	f
63	linkin park	6XyY86QOPPrYVGvF9ch6wz	https://i.scdn.co/image/ab6761610000e5eb527d95dabbe8b8b527e8136f	Linkin Park, formed in 1996, revolutionized the nu-metal genre with their debut album 'Hybrid Theory,' which included hits like 'In the End' and 'One Step Closer.' The band's fusion of rock, hip-hop, and electronic music has influenced countless artists. Tragically, the loss of lead vocalist Chester Bennington in 2017 marked a significant moment in their history, yet their legacy continues to inspire fans worldwide.	f
64	green day	7oPftvlwr6VrsViSDV7fJY	https://i.scdn.co/image/ab6761610000e5eb6ff0cd5ef2ecf733804984bb	Green Day, formed in 1987, is a punk rock band that gained mainstream success with their album 'Dookie' in 1994. Their politically charged album 'American Idiot' in 2004 revitalized their career and earned them a Grammy Award for Best Rock Album. Known for their energetic live performances and catchy melodies, Green Day has been a significant influence on pop-punk and alternative rock.	f
65	red hot chili peppers	0L8ExT028jH3ddEcZwqJJ5	https://i.scdn.co/image/ab6761610000e5ebc33cc15260b767ddec982ce8	Red Hot Chili Peppers, formed in 1983, are known for their unique blend of funk, punk, and rock music. With iconic albums like 'Blood Sugar Sex Magik' and hits like 'Under the Bridge,' they have achieved widespread acclaim and multiple Grammy Awards. Their energetic performances and innovative style have made them one of the most influential bands in alternative rock.	f
66	3 doors down	2RTUTCvo6onsAnheUk3aL9	https://i.scdn.co/image/ab6761610000e5eb2064b57344edc592454c8090	3 Doors Down, formed in 1996, gained fame with their debut single 'Kryptonite,' which became a rock staple. Their music often explores themes of personal struggle and resilience, resonating with a wide audience. The band has continued to release successful albums and tour extensively, maintaining a strong fan base.	f
67	papa roach	4RddZ3iHvSpGV4dvATac9X	https://i.scdn.co/image/ab6761610000e5eb170958adc93250084c317cfc	Papa Roach, formed in 1993, broke into the mainstream with their album 'Infest,' featuring the hit 'Last Resort.' Known for their nu-metal sound and later forays into alternative rock, they have maintained a dedicated following. Their music often addresses personal and social issues, making them a significant voice in the rock scene.	f
68	the white stripes	4F84IBURUo98rz4r61KF70	https://i.scdn.co/image/ab6761610000e5eb70cc06de8fc28226d4743cd9	The White Stripes, formed by Jack and Meg White in 1997, are known for their minimalist approach to rock music, often using only guitar, drums, and vocals. Their album 'Elephant' and the hit 'Seven Nation Army' have become iconic in the rock genre. The band's influence extends beyond music, impacting fashion and art with their distinctive red, white, and black aesthetic.	f
69	the killers	0C0XlULifJtAgn6ZNCW2eu	https://i.scdn.co/image/ab6761610000e5eb207b21f3ed0ee96adce3166a	The Killers, formed in 2001, are known for their synth-infused rock sound and catchy hits like 'Mr. Brightside' and 'Somebody Told Me.' Their debut album 'Hot Fuss' became a commercial success, and they have since released several acclaimed albums. The band's ability to blend new wave, indie, and pop elements has made them a staple in modern rock music.	f
70	train	3FUY2gzHeIiaesXtOAdB7A	https://i.scdn.co/image/ab6761610000e5ebeb96a88993a929eaadbe4864	Train, formed in 1993, achieved mainstream success with their hit 'Drops of Jupiter (Tell Me),' which won two Grammy Awards. Known for their melodic rock and pop sound, they have continued to release popular songs like 'Hey, Soul Sister.' Their music often features introspective lyrics and catchy hooks, appealing to a broad audience.	f
71	lifehouse	5PokPZn11xzZXyXSfnvIM3	https://i.scdn.co/image/ab6761610000e5eb621cdc23c3db9d37d780762e	Lifehouse, formed in 1999, gained fame with their debut single 'Hanging by a Moment,' which became a defining song of the early 2000s. Their music blends rock and pop elements, often focusing on themes of love and personal growth. The band has maintained a loyal fan base and continues to release new music.	f
72	jimmy eat world	3Ayl7mCk0nScecqOzvNp6s	https://i.scdn.co/image/ab6761610000e5eb0dc33cfd207772f8e2f6b46f	Jimmy Eat World, formed in 1993, became known for their emo and alternative rock sound, particularly with their hit 'The Middle.' Their album 'Bleed American' solidified their place in the music scene, and they have since released several successful albums. Known for their catchy melodies and introspective lyrics, they have influenced many bands in the emo genre.	f
73	panic at the disco	20JZFwl6HVl6yg8a4H3ZqK	https://i.scdn.co/image/ab6761610000e5ebb256ae9a4b82bfff97776ae2	Panic! at the Disco, formed in 2004, gained fame with their debut album 'A Fever You Can't Sweat Out' and the hit 'I Write Sins Not Tragedies.' The band's music has evolved from emo and pop-punk to a more pop-oriented sound. Led by frontman Brendon Urie, they have continued to release successful albums and maintain a strong fan base.	f
74	gorillaz	3AA28KZvwAUcZuOKwyblJQ	https://i.scdn.co/image/ab6761610000e5eb8699856fde13105fa01279ad	Gorillaz, created by Damon Albarn and Jamie Hewlett in 1998, is a virtual band known for their innovative blend of alternative rock, hip-hop, and electronic music. Their debut album 'Gorillaz' and hits like 'Clint Eastwood' have been critically acclaimed. The band's use of animated characters and storytelling has set them apart in the music industry.	f
75	de la soul	1Z8ODXyhEBi3WynYw0Rya6	https://i.scdn.co/image/ab6761610000e5ebc443011311dcf7f6eeaf507d	De La Soul, formed in 1987, is known for their debut album '3 Feet High and Rising,' which introduced a new style of hip-hop with its eclectic sampling and positive lyrics. They have been influential in the development of alternative hip-hop and have won a Grammy Award for Best Pop Collaboration with Vocals. Their innovative approach to music and culture continues to inspire new generations.	f
76	shaun ryder	3ONSkkEnOSZVNogu98dvTY	https://i.scdn.co/image/ab6772690000c46cd7bc7201def92f45d79cabbe	Shaun Ryder, known for his work with Happy Mondays and Black Grape, is a key figure in the Madchester scene of the late 1980s and early 1990s. His distinctive vocal style and provocative lyrics have made him a cult icon. Ryder's influence extends beyond music, as he has also appeared on reality TV shows, showcasing his unique personality.	f
77	foo fighters	7jy3rLJdDQY21OgRLCZ9sD	https://i.scdn.co/image/ab6761610000e5eb07be1890ac379235723258de	Foo Fighters, formed by Dave Grohl in 1994, emerged from the ashes of Nirvana to become one of the most successful rock bands of the 2000s. Known for hits like 'Everlong' and 'Learn to Fly,' they have won multiple Grammy Awards. Their music blends hard rock with melodic elements, appealing to a wide audience.	f
78	hoobastank	2MqhkhX4npxDZ62ObR5ELO	https://i.scdn.co/image/ab6761610000e5ebb6f14120a7c97c531c2ebdcc	Hoobastank, formed in 1994, gained fame with their hit 'The Reason,' which became a defining song of the early 2000s. Their music blends alternative rock with post-grunge elements, often focusing on themes of personal struggle and redemption. The band has continued to release music and tour, maintaining a dedicated fan base.	f
79	evanescence	5nGIFgo0shDenQYSE0Sn7c	https://i.scdn.co/image/ab6761610000e5eb7ecf213c7dd78e0049379c5b	Evanescence, formed in 1995, gained fame with their debut album 'Fallen' and the hit 'Bring Me to Life.' Known for their blend of gothic rock and symphonic elements, they have won multiple awards, including two Grammy Awards. The band's music often explores themes of personal struggle and empowerment, resonating with a wide audience.	f
80	system of a down	5eAWCfyUhZtHHtBdNk56l1	https://i.scdn.co/image/ab6761610000e5eb60063d3451ade8f9fab397c2	System of a Down, formed in 1994, is known for their unique blend of alternative metal, hard rock, and Armenian folk music. Their politically charged lyrics and hits like 'Chop Suey!' and 'B.Y.O.B.' have earned them a dedicated following. The band has won a Grammy Award and continues to influence the rock genre.	f
81	franz ferdinand	0XNa1vTidXlvJ2gHSsRi4A	https://i.scdn.co/image/ab6761610000e5eb69ecfa7557856564c968640d	Franz Ferdinand, formed in 2002, gained fame with their debut album and the hit 'Take Me Out.' Known for their post-punk revival sound, they have won multiple awards, including a Mercury Prize. Their music often features catchy melodies and danceable rhythms, making them a staple in indie rock.	f
82	yeah yeah yeahs	3TNt4aUIxgfy9aoaft5Jj2	https://i.scdn.co/image/ab6761610000e5eb746654923d25b6bf7c16e899	Yeah Yeah Yeahs, formed in 2000, are known for their art punk and indie rock sound, with hits like 'Maps' and 'Heads Will Roll.' Led by frontwoman Karen O, they have been influential in the indie scene and have won a Grammy Award. Their music often blends raw energy with emotional depth, resonating with fans.	f
83	modest mouse	1yAwtBaoHLEDWAnWR87hBT	https://i.scdn.co/image/ab6761610000e5eb39b413eb76d2ae87496d76b8	Modest Mouse, formed in 1992, gained fame with their album 'Good News for People Who Love Bad News' and the hit 'Float On.' Known for their indie rock sound and introspective lyrics, they have been influential in the indie scene. The band's music often explores themes of existentialism and social commentary.	f
84	maroon 5	04gDigrS5kc9YWfZHwBETP	https://i.scdn.co/image/ab6761610000e5ebf8349dfb619a7f842242de77	Maroon 5, formed in 1994, gained fame with their debut album 'Songs About Jane' and hits like 'This Love' and 'She Will Be Loved.' Known for their pop-rock sound and catchy melodies, they have won multiple Grammy Awards. The band's music often features themes of love and relationships, appealing to a broad audience.	f
85	the rembrandts	0gDg7FEsF4Y1jWddJJgcn4	https://i.scdn.co/image/ab6761610000e5eb203cbc1f8dbeac5b4993581a	The Rembrandts are an American pop rock duo best known for their hit song 'I'll Be There for You,' which served as the theme song for the television sitcom Friends. Their music often blends elements of pop and rock, with catchy melodies and harmonies. The success of 'I'll Be There for You' significantly boosted their career, leading to increased recognition and a lasting legacy in pop culture.	f
86	gary portnoy	53U1IJqr6Hhmn53UcbgF7D	https://i.scdn.co/image/ab67616d0000b2736bb85ed5053d24308e49d961	Gary Portnoy is an American singer-songwriter famous for co-writing and performing the theme songs for the television shows Cheers and Punky Brewster. His work on 'Where Everybody Knows Your Name' for Cheers earned him a Primetime Emmy Award nomination. Portnoy's contributions to television themes have left a lasting impact on the genre, blending catchy tunes with memorable lyrics.	f
87	dj jazzy jeff and the fresh prince	1mG23iQeR29Ojhq89D5gbh	https://i.scdn.co/image/3194246bd54b76c376e2be5a21a61dd7b93aeeb9	DJ Jazzy Jeff & The Fresh Prince, consisting of DJ Jazzy Jeff and Will Smith, were pioneers in the hip-hop genre, known for their light-hearted and comedic approach to music. They won the first-ever Grammy Award for Best Rap Performance in 1989 for their hit 'Parents Just Don't Understand.' Their influence extended beyond music, with Will Smith's successful transition to acting, impacting both music and entertainment industries.	f
88	andrew gold	5fmvGUlMVgmnCn45f1he7d	https://i.scdn.co/image/ab6761610000e5eb5b80adaab28dc1d9bc464eaf	Andrew Gold was an American singer, songwriter, and musician known for his hit singles 'Lonely Boy' and 'Thank You for Being a Friend,' the latter becoming the theme song for The Golden Girls. His versatile musical style ranged from pop to rock, and he was also a skilled session musician, contributing to albums by artists like Linda Ronstadt. Gold's work has left a lasting legacy in both the pop and television music genres.	f
89	janet dubois	1Cj6mWmO7c0HBuHNGSmOOg	https://i.scdn.co/image/ab67616d0000b273dc65e384a8fb04cf07775e02	Janet DuBois was an American actress and singer best known for her role as Willona Woods on the television show Good Times. She also wrote and performed the theme song for The Jeffersons, 'Movin' On Up,' which became a cultural phenomenon. DuBois' contributions to television and music have cemented her place in entertainment history.	f
90	jeff barry	4h4nyO6EOTwCGe7LwwHR4I	https://i.scdn.co/image/ffcb330904f039341a64c00f8c4cc4a853fa5f70	Jeff Barry is an American pop music songwriter, singer, and record producer known for co-writing numerous hit songs in the 1960s, including 'Sugar Town' and 'I'm a Believer.' His work with Ellie Greenwich produced many classic tracks that defined the era's pop sound. Barry's influence on pop music is profound, with his songs continuing to be celebrated and covered by artists across generations.	f
91	the brady bunch	1b5kd4esL2zG9nhXz65b8K	https://i.scdn.co/image/ab67616d0000b2734cc5ae1a7de063cb700b725d	The Brady Bunch was a fictional family from the popular 1970s television show of the same name, who also released several albums and singles. Their most famous song, 'Sunshine Day,' captured the wholesome and upbeat spirit of the show. The Brady Bunch's music has become a nostalgic part of pop culture, often remembered fondly by fans of the series.	f
92	jack marshall	3Aph9hft9LO5087r28M3MZ	https://i.scdn.co/image/ab6761610000e5eb51b788e4c730718fff40fa4c	Jack Marshall was an American guitarist, conductor, and composer known for his work on television themes, including the theme for The Munsters. He was a prolific session musician and arranger, contributing to numerous recordings across various genres. Marshall's distinctive guitar work and compositions have left a lasting impact on the sound of television in the 1960s.	f
93	flatt and scruggs	1iNNWK8bYjc5EK0waLk1J1	https://i.scdn.co/image/02b9a077c9972ca7d79069f1485da39e82634af4	Flatt and Scruggs were an influential American bluegrass duo, consisting of Lester Flatt and Earl Scruggs. They are best known for their theme song for The Beverly Hillbillies, 'The Ballad of Jed Clampett,' which became a crossover hit. Their innovative style and virtuosity on the banjo and guitar helped define and popularize bluegrass music.	f
94	earle hagen	2yAjgGMoWrfjWXnZ63ynP5	https://i.scdn.co/image/ab67616d0000b273f79eb984a5d87231fa8a6ea1	Earle Hagen was an American composer best known for creating the themes for The Andy Griffith Show and The Dick Van Dyke Show. His work in television music earned him multiple Emmy Awards, and his themes are some of the most recognizable in television history. Hagen's contributions to the genre have had a lasting impact on the sound of classic TV shows.	f
95	marius constant	0TFFISao0xA2ax2vkzbN0l	https://i.scdn.co/image/ab67616d0000b27311c0f478c6f6f61bd5641c2e	Marius Constant was a Romanian-born French composer known for creating the iconic theme for The Twilight Zone. His work in film and television music blended classical and modern elements, creating a unique and haunting sound. Constant's theme for The Twilight Zone remains one of the most recognized and influential pieces in television history.	f
96	boston pops orchestra	7CIcEIOiWaZcEH35cpsdZq	https://i.scdn.co/image/ab6761610000e5ebabee00ff8d2e08f97d7d1ac7	The Boston Pops Orchestra is an American orchestra based in Boston, Massachusetts, known for its performances of popular and light classical music. They have recorded numerous television themes, including the theme for The Lawrence Welk Show. The Boston Pops' contributions to television music have helped bridge the gap between classical and popular music, bringing orchestral arrangements to a wider audience.	f
97	the ventures	2GaayiIs1kcyNqRXQuzp35	https://i.scdn.co/image/ab6761610000e5eb48d2552358f9c87c67f21d55	The Ventures are an American instrumental rock band known for their hit 'Walk, Don't Run,' which became a surf rock classic. They have also recorded numerous television themes, including the theme for Hawaii Five-O. The Ventures' influence on instrumental rock and their prolific output of television themes have cemented their place in music history.	f
98	lalo schifrin	39iHRO9MH9To3gjW7wqaW1	https://i.scdn.co/image/eb76a42d736645df1fd87f88e9dc57297a181698	Lalo Schifrin is an Argentine-American composer, conductor, and pianist known for his work on film and television scores, including the theme for Mission: Impossible. His innovative use of jazz and Latin elements in his compositions has earned him multiple Grammy and Emmy Awards. Schifrin's work has had a significant impact on the sound of action and thriller genres.	f
99	henry mancini	2EExdpjU4SK3xnJHO5paJf	https://i.scdn.co/image/ab6761610000e5eb9ee0e74df9f9ee5745caf24c	Henry Mancini was an American composer and conductor known for his iconic film and television scores, including the themes for The Pink Panther and Peter Gunn. His work earned him numerous Academy and Grammy Awards, and his compositions are celebrated for their sophistication and catchiness. Mancini's influence on film and television music is profound, with his themes remaining popular and influential.	f
100	walter schumann	3867gCebd7mtrAXTgWV3kU	\N	Walter Schumann was an American composer and conductor known for creating the theme for the television series Dragnet. His work in television and film music helped define the sound of crime dramas in the 1950s. Schumann's theme for Dragnet is one of the most recognizable and influential pieces in television history.	f
101	ray anthony and his orchestra	5QW6Fuf8rC85McLea15MaK	https://i.scdn.co/image/ab67616d0000b2731994b0cd05a5a981c78c946c	Ray Anthony and His Orchestra are an American big band known for their renditions of popular songs and television themes, including the theme for Peter Gunn. Their music blends elements of swing and jazz, creating a lively and danceable sound. Ray Anthony's contributions to television music have helped keep the big band sound alive in popular culture.	f
102	plas johnson	4Xqx9yiQsWMNXE2oKbm5uc	https://i.scdn.co/image/9cca5075c47514a22fac9ce2d5f04640d5752620	Plas Johnson is an American saxophonist known for his work on numerous television themes, including the theme for The Pink Panther. His distinctive saxophone sound has been featured on countless recordings across various genres. Johnson's contributions to television music have helped define the sound of many classic TV shows.	f
103	neal hefti	3IjVHk8Mo8GBMKyHnwmth8	https://i.scdn.co/image/ab67616d0000b273fbdd11fc5c3be27892bdc496	Neal Hefti was an American jazz trumpeter, composer, and arranger known for creating the themes for The Odd Couple and Batman. His work in television and film music blended jazz and pop elements, creating catchy and memorable themes. Hefti's influence on television music is significant, with his themes remaining popular and iconic.	f
104	alexander courage	2qLGUeF6YNEfR2lyzY6Nah	https://i.scdn.co/image/ab67616d0000b2730edc5013d2cf80371d904dbc	Alexander Courage was an American orchestrator, arranger, and composer known for creating the theme for Star Trek. His work in film and television music earned him multiple Emmy Awards, and his themes are some of the most recognizable in science fiction. Courage's contributions to the genre have had a lasting impact on the sound of space exploration in media.	f
105	fred steiner	7IL5hGayYCP22e908cdChk	https://i.scdn.co/image/ab67616d0000b27349fdfbdf1bcbe3392e895f7b	Fred Steiner was an American composer, conductor, and orchestrator known for his work on television themes, including the theme for Perry Mason. His compositions often blended classical and modern elements, creating a unique and memorable sound. Steiner's contributions to television music have helped define the sound of many classic TV shows.	f
106	danny elfman	5qBZETtyzfYnXOobDXbmcD	https://i.scdn.co/image/ab6761610000e5ebf741706530dbd36d43078b98	Danny Elfman is an American composer, singer, and songwriter known for his work on film and television scores, including the themes for The Simpsons and Batman. His distinctive style blends elements of rock, pop, and classical music, creating memorable and iconic themes. Elfman's influence on film and television music is profound, with his themes remaining popular and influential.	f
107	the city of prague philharmonic orchestra	2oQJQUIpJFFnfKvHJA0xBu	https://i.scdn.co/image/ab6761610000e5eb8c6007c4950dd2361e50be9a	The City of Prague Philharmonic Orchestra is a Czech orchestra known for its recordings of film and television scores, including themes for various movies and TV shows. Their work has helped bring orchestral arrangements to a wider audience, bridging the gap between classical and popular music. The City of Prague Philharmonic's contributions to television music have been significant, with their recordings being used in numerous productions.	f
108	mark snow	0JG0Qap3zA5NciJOzIalt3	https://i.scdn.co/image/3aaf8bd64f082c24247067aa4afb6f705a2d7389	Mark Snow is an American composer known for creating the theme for The X-Files. His work in television and film music blends elements of electronic and orchestral music, creating a unique and haunting sound. Snow's contributions to the genre have had a lasting impact on the sound of science fiction and mystery in media.	f
109	mike post	2roaPGR1goiiLQxrG5dXiF	https://i.scdn.co/image/ab6761610000e5ebbfab18ee720b5158673f4e08	Mike Post is an American composer and record producer known for creating themes for numerous television shows, including The A-Team and Law & Order. His work in television music has earned him multiple Emmy Awards, and his themes are some of the most recognizable in the genre. Post's influence on television music is significant, with his themes remaining popular and influential.	f
110	the who	67ea9eGLXYMsO2eYQRui3w	https://i.scdn.co/image/9cd709cabb4a614b4f1dd9ec256a5f30e21f0150	The Who are an English rock band known for their hit songs 'My Generation' and 'Baba O'Riley,' the latter of which was used as the theme for CSI: Crime Scene Investigation. Their music blends elements of rock, pop, and experimental sounds, creating a unique and influential style. The Who's contributions to rock music and their use in television themes have cemented their place in music history.	f
111	alabama 3	25zUD40u8M2kJmdcabBzrz	https://i.scdn.co/image/ab6761610000e5eb5ae7890c4d13f635f5117e94	Alabama 3 are a British band known for their eclectic style, blending elements of rock, electronica, and country. They are best known for their song 'Woke Up This Morning,' which was used as the theme for The Sopranos. Alabama 3's unique sound and their contribution to television music have made them a notable presence in the music industry.	f
112	wg snuffy walden	1o9c8sfXo2HKF95bWvPUbN	https://i.scdn.co/image/ab67616d0000b2739ed595fe03a14d749ed56658	W.G. Snuffy Walden is an American composer and musician known for creating the themes for The West Wing and My So-Called Life. His work in television music blends elements of rock and orchestral music, creating a unique and memorable sound. Walden's contributions to the genre have had a lasting impact on the sound of drama and political shows.	f
113	james newton howard	2M4eNCvV3CJUswavkhAQg2	https://i.scdn.co/image/ab6761610000e5ebe9d190a9e39a772d84b068ab	James Newton Howard is an American composer known for his work on film and television scores, including the themes for ER and Pretty Woman. His compositions often blend elements of orchestral and electronic music, creating a sophisticated and emotive sound. Howard's influence on film and television music is significant, with his themes remaining popular and influential.	f
114	phantom planet	0LsTFjEB1IIrh7IlTxs1GY	https://i.scdn.co/image/ab6761610000e5eb7a0c1e8ecd58c1fdede23a25	Phantom Planet are an American rock band known for their hit song 'California,' which was used as the theme for The O.C. Their music blends elements of pop and rock, creating a catchy and energetic sound. Phantom Planet's contribution to television music has helped define the sound of teen dramas in the early 2000s.	f
115	lazlo bane	2jI9rHOuUAPJEULovOfgyB	https://i.scdn.co/image/ab6761610000e5eb1290ac08174212090f41ac5d	Lazlo Bane are an American alternative rock band known for their song 'Superman,' which was used as the theme for Scrubs. Their music blends elements of rock and pop, creating a catchy and uplifting sound. Lazlo Bane's contribution to television music has helped define the sound of medical comedies.	f
116	the scrantones	7kTw12ClOvpgRqtogHeG3J	https://i.scdn.co/image/ab67616d0000b2731f377fca5b39a58ee3728e9b	The Scrantones are an American rock band known for their song 'The Office Theme,' which was used as the theme for the television show The Office. Their music blends elements of rock and pop, creating a catchy and memorable sound. The Scrantones' contribution to television music has helped define the sound of workplace comedies.	f
117	dashiin	22qwq4EH17QsRkZWMEhelR	\N	Dashiin is an American composer known for creating the theme for the television show Breaking Bad. His work in television music blends elements of electronic and orchestral music, creating a unique and haunting sound. Dashiin's contributions to the genre have had a lasting impact on the sound of crime dramas.	f
118	michael giacchino	4kLvhMAuCloLxoP1aVM7Lr	https://i.scdn.co/image/ab6761610000e5eb9945209ac13720afd7eea2e3	Michael Giacchino is an American composer known for his work on film and television scores, including the themes for Lost and Up. His compositions often blend elements of orchestral and electronic music, creating a sophisticated and emotive sound. Giacchino's influence on film and television music is significant, with his themes remaining popular and influential.	f
119	massive attack	6FXMGgJwohJLUSr5nVlf9X	https://i.scdn.co/image/c8bbeedb05f38ae5cb982a7daf4bf7129cca892c	Massive Attack are a British electronic music group known for their song 'Teardrop,' which was used as the theme for House. Their music blends elements of trip-hop, electronica, and ambient sounds, creating a unique and atmospheric style. Massive Attack's contribution to television music has helped define the sound of medical dramas.	f
120	horace andy	2ieAXAuLe6qQ3RJsqCxpoC	https://i.scdn.co/image/ab6772690000c46ca60968641586880e27d0daff	Horace Andy is a Jamaican reggae singer known for his work with Massive Attack, including the song 'Angel,' which was used as the theme for Peaky Blinders. His distinctive vocal style and collaborations with various artists have made him a notable figure in reggae and electronic music. Andy's contribution to television music has helped bring reggae to a wider audience.	f
121	sean callery	1mSdzR53wTsiokwyE8BJkl	https://i.scdn.co/image/ab6761610000e5eb6bd6ed70bbedcd153d6f5aa0	Sean Callery is an American composer known for creating the themes for 24 and Homeland. His work in television music blends elements of electronic and orchestral music, creating a unique and intense sound. Callery's contributions to the genre have had a lasting impact on the sound of action and thriller shows.	f
122	tom waits	7x83XhcMbOTl1UdYsPTuZM	https://i.scdn.co/image/ab6761610000e5eb4679f0c1c8f862730c0b5109	Tom Waits is an American singer-songwriter known for his distinctive gravelly voice and eclectic style, blending elements of blues, jazz, and rock. He contributed the song 'Way Down in the Hole,' which was used as the theme for The Wire. Waits' contribution to television music has helped define the sound of crime dramas.	f
123	dave porter	1WkfFuCfD2BnsiyPElbEv5	https://i.scdn.co/image/ab6761610000e5eb7cbfba01b0dd0bc6ba7ac3e5	Dave Porter is an American composer known for creating the theme for Breaking Bad and its spin-off Better Call Saul. His work in television music blends elements of electronic and orchestral music, creating a unique and haunting sound. Porter's contributions to the genre have had a lasting impact on the sound of crime dramas.	f
124	rjd2	1O3ZOjqFLEnbpZexcRjocn	https://i.scdn.co/image/ab6772690000c46c2e0662f18cc4b8676f3ecedd	RJD2 is an American musician and producer known for his work in hip-hop and electronic music. He contributed the song 'A Beautiful Mine,' which was used as the theme for Mad Men. RJD2's contribution to television music has helped define the sound of period dramas.	f
125	jace everett	47DQBkDU2VieRG0aJUcPJs	https://i.scdn.co/image/ab6761610000e5eb1e063ca95f9cfc5f1322cd2e	Jace Everett is an American singer-songwriter known for his song 'Bad Things,' which was used as the theme for True Blood. His music blends elements of country and rock, creating a unique and atmospheric sound. Everett's contribution to television music has helped define the sound of supernatural dramas.	f
126	rolfe kent	3B0bZAXnHTpGuPsuQo5fEd	https://i.scdn.co/image/ab6761610000e5ebd77a92a28c37f7bb9de45dba	Rolfe Kent is an American composer known for his work on film and television scores, including the themes for Dexter and Legally Blonde. His compositions often blend elements of orchestral and electronic music, creating a sophisticated and emotive sound. Kent's influence on film and television music is significant, with his themes remaining popular and influential.	f
127	malvina reynolds	5fhMeS3lpUqUpTNuAxU2rN	https://i.scdn.co/image/ab67616d0000b2737cdea96511f9e03e3b1b1308	Malvina Reynolds was an American folk singer and songwriter known for her song 'Little Boxes,' which was used as the theme for Weeds. Her music often addressed social and political issues, blending elements of folk and protest songs. Reynolds' contribution to television music has helped bring folk music to a wider audience.	f
128	mark mothersbaugh	5sEDTHJJyDEWVFx99hGSIb	https://i.scdn.co/image/ab6761610000e5ebd707bc90aea4229d20d91682	Mark Mothersbaugh is an American composer, musician, and singer known for his work on film and television scores, including the themes for The Lego Movie and Rugrats. His compositions often blend elements of rock, pop, and electronic music, creating a unique and playful sound. Mothersbaugh's influence on film and television music is significant, with his themes remaining popular and influential.	f
\.


--
-- Data for Name: decade; Type: TABLE DATA; Schema: core_tables; Owner: postgres
--

COPY core_tables.decade (id, decade_name, display_name) FROM stdin;
1	2010s	\N
2	2000s	\N
\.


--
-- Data for Name: genre; Type: TABLE DATA; Schema: core_tables; Owner: postgres
--

COPY core_tables.genre (id, genre_name, display_name) FROM stdin;
1	country	\N
2	pop	\N
3	rock	\N
4	TV Themes	\N
\.


--
-- Data for Name: language; Type: TABLE DATA; Schema: core_tables; Owner: postgres
--

COPY core_tables.language (code, name) FROM stdin;
\.


--
-- Data for Name: specialty; Type: TABLE DATA; Schema: core_tables; Owner: postgres
--

COPY core_tables.specialty (id, specialty_name, display_name) FROM stdin;
\.


--
-- Data for Name: artist_genre; Type: TABLE DATA; Schema: join_tables; Owner: postgres
--

COPY join_tables.artist_genre (id, artist_id, genre_id) FROM stdin;
1	1	1
2	2	1
3	3	1
4	4	1
5	5	1
6	6	1
7	7	1
8	8	1
9	9	1
10	10	1
11	11	1
12	12	1
13	13	1
14	14	1
15	15	1
16	16	1
17	17	1
18	18	1
19	19	1
20	20	1
21	21	2
22	22	2
23	23	2
24	24	2
25	25	2
26	26	2
27	27	2
28	28	2
29	29	2
30	30	2
31	31	2
32	32	2
33	33	2
34	34	2
35	35	2
36	36	2
37	37	2
38	38	2
39	39	2
40	40	2
41	41	2
42	42	2
43	43	2
44	44	2
45	45	2
46	46	2
47	47	2
48	48	2
49	49	2
50	50	2
51	51	2
52	52	2
53	53	2
54	54	2
55	55	2
56	56	2
57	57	2
58	58	2
59	59	2
60	60	2
61	61	2
62	62	3
63	63	3
64	64	3
65	65	3
66	66	3
67	67	3
68	68	3
69	69	3
70	70	3
71	71	3
72	72	3
73	73	3
74	74	3
75	75	3
76	76	3
77	77	3
78	59	3
79	78	3
80	22	3
81	79	3
82	54	3
83	80	3
84	81	3
85	82	3
86	83	3
87	84	3
88	85	4
89	86	4
90	87	4
91	88	4
92	89	4
93	90	4
94	91	4
95	92	4
96	93	4
97	94	4
98	95	4
99	96	4
100	97	4
101	98	4
102	99	4
103	100	4
104	101	4
105	102	4
106	103	4
107	104	4
108	105	4
109	106	4
110	107	4
111	108	4
112	109	4
113	110	4
114	111	4
115	112	4
116	113	4
117	114	4
118	115	4
119	116	4
120	117	4
121	118	4
122	119	4
123	120	4
124	121	4
125	122	4
126	123	4
127	124	4
128	125	4
129	126	4
130	127	4
131	128	4
\.


--
-- Data for Name: decade_genre; Type: TABLE DATA; Schema: join_tables; Owner: postgres
--

COPY join_tables.decade_genre (id, decade_id, genre_id) FROM stdin;
1	1	1
2	2	1
3	2	2
4	2	3
5	2	4
\.


--
-- Data for Name: track_genre; Type: TABLE DATA; Schema: join_tables; Owner: postgres
--

COPY join_tables.track_genre (track_id, genre_id) FROM stdin;
\.


--
-- Data for Name: specialty_ranking; Type: TABLE DATA; Schema: ranking_tables; Owner: postgres
--

COPY ranking_tables.specialty_ranking (id, track_id, specialty_id, tracklist_id, ranking, intro, detail, artist_id, ranking_date, intro_mp3_url) FROM stdin;
\.


--
-- Data for Name: top40_genre_ranking; Type: TABLE DATA; Schema: ranking_tables; Owner: postgres
--

COPY ranking_tables.top40_genre_ranking (id, genre_id, artist_id, track_id, ranking, info, detail, ranking_date, intro_mp3_url) FROM stdin;
\.


--
-- Data for Name: track_ranking; Type: TABLE DATA; Schema: ranking_tables; Owner: postgres
--

COPY ranking_tables.track_ranking (id, track_id, decade_genre_id, tracklist_id, ranking, intro, ranking_date) FROM stdin;
2	1	1	1	1	Ranked #1 in the 2010s, 'Cruise' by Florida Georgia Line from the album Here's To The Good Times is a country hit that'll get you moving!	2025-07-26
3	2	1	1	2	At #2 in the 2010s, Thomas Rhett's 'Die A Happy Man' from the album Tangled Up is a country ballad that tugs at the heartstrings.	2025-07-26
4	3	2	1	1	Kicking off the 2000s country hits at rank 1, Lee Ann Womack's 'I Hope You Dance' from the album I Hope You Dance invites us to live fully!	2025-07-24
5	4	2	1	2	Dramatic and poignant, Alan Jackson's 'Where Were You When the World Stopped Turning' from the album Drive captures a nation's grief, ranking 2 in the 2000s country charts.	2025-07-24
6	5	2	1	3	Did you know? Lonestar's 'Amazed' from the album Lonely Grill, a romantic ballad, secured the 3rd spot in the 2000s country music scene!	2025-07-24
7	6	2	1	4	Patriotic fervor hits the charts at number 4 with Toby Keith's 'Courtesy of the Red, White and Blue (The Angry American)' from the album Unleashed.	2025-07-24
8	7	2	1	5	Alan Jackson strikes again at rank 5 with 'It's Five O'Clock Somewhere' from the album Greatest Hits Volume II, a playful anthem for early drinkers!	2025-07-24
9	8	2	1	6	Breaking the mold at number 6, Gretchen Wilson's 'Redneck Woman' from the album Here For The Party celebrates unapologetic country pride.	2025-07-24
10	9	2	1	7	Saddle up for fun! Big and Rich's 'Save a Horse (Ride a Cowboy)' from the album Horse of a Different Color gallops to the 7th spot in the 2000s.	2025-07-24
11	10	2	1	8	Sara Evans washes into the 8th position with 'Suds in the Bucket' from the album Restless, a fresh take on love and laundry!	2025-07-24
12	11	2	1	9	As the sun sets on the 9th rank, Kenny Chesney's 'When the Sun Goes Down' from the album When The Sun Goes Down serenades us into the night.	2025-07-24
13	12	2	1	10	Closing the top 10 with a powerful message, Tim McGraw's 'Live Like You Were Dying' from the album Live Like You Were Dying inspires us to seize the day.	2025-07-24
14	13	2	1	11	Ranked 11th in the 2000s, Lonestar's 'I'm Already There' from the album I'm Already There, is a country classic that tugs at the heartstrings.	2025-07-24
15	14	2	1	12	Crack open a cold one with Toby Keith's 'Beer For My Horses', hitting number 12 in the 2000s country charts, straight from the album Unleashed!	2025-07-24
16	15	2	1	13	Did you know Rascal Flatts' 'Mayberry' ranked 13th in the 2000s? This country gem is featured on the album Melt.	2025-07-24
17	16	2	1	14	Bless your ears with Rascal Flatts' 'Bless The Broken Road', a touching country hit from the 2000s, ranking 14th, from the album Feels Like Today.	2025-07-24
18	17	2	1	15	Keith Urban's 'Days Go By' cruises into the 15th spot in the 2000s country rankings, a smooth ride from the album Be Here.	2025-07-24
19	18	2	1	16	Feel the charm of Keith Urban's 'Somebody Like You', securing the 16th rank in the 2000s country scene, from the album Golden Road.	2025-07-24
20	19	2	1	17	Keith Urban's 'You'll Think Of Me' clinches the 17th position in the 2000s, a poignant country tune from the album Golden Road.	2025-07-24
21	20	2	1	18	Rascal Flatts keeps moving with 'I'm Movin' On', ranking 18th in the 2000s country hits, from their self-titled album Rascal Flatts.	2025-07-24
22	21	2	1	19	Rascal Flatts reflects on 'These Days', landing at number 19 in the 2000s country charts, featured on the album Melt.	2025-07-24
23	22	2	1	20	Rev up for Rascal Flatts' 'Fast Cars And Freedom', speeding to the 20th spot in the 2000s, from the album Feels Like Today.	2025-07-24
24	23	2	1	21	Ranked 21 in the 2000s, 'What Hurts The Most' by Rascal Flatts from the album Me And My Gang is a country classic that tugs at the heartstrings!	2025-07-24
25	24	2	1	22	Dive into the 2000s with 'My Wish' by Rascal Flatts, hitting rank 22 in country music, straight from the album Me And My Gang.	2025-07-24
26	25	2	1	23	At number 23, 'Stand' by Rascal Flatts from the album Life Is A Highway: Refueled Duets, showcases their enduring presence in 2000s country music.	2025-07-24
27	26	2	1	24	Feel the thrill of the open road with 'Life Is A Highway' by Rascal Flatts, ranking 24 in the 2000s country genre, from Me And My Gang.	2025-07-24
28	27	2	1	25	Discover the touching story of 'Skin Sarabeth' by Rascal Flatts, ranked 25 in the 2000s, featured on the album Feels Like Today.	2025-07-24
29	28	2	1	26	Brad Paisley's 'She's Everything' captures hearts at rank 26, a 2000s country gem from the album Time Well Wasted.	2025-07-24
30	29	2	1	27	Experience the poignant 'Whiskey Lullaby' by Brad Paisley, ranking 27 in the 2000s country charts, from the album Hits Alive.	2025-07-24
31	30	2	1	28	Get down and dirty with 'Mud On The Tires' by Brad Paisley, securing spot 28 in the 2000s, from the album Mud On The Tires.	2025-07-24
32	31	2	1	29	Raise a glass to 'Alcohol' by Brad Paisley, a fun track that reached rank 29 in the 2000s, from Time Well Wasted.	2025-07-24
33	32	2	1	30	Laugh along with 'Ticks' by Brad Paisley, hitting number 30 in the 2000s country scene, from the album 5th Gear.	2025-07-24
34	33	2	1	31	Dive into the 31st-ranked country hit of the 2000s, 'Letter to Me' by Brad Paisley, from the album 5th Gear. It's a playful reflection on life's lessons!	2025-07-24
35	34	2	1	32	At number 32, 'Online' by Brad Paisley from 5th Gear takes the stage. This 2000s country track humorously explores the digital world.	2025-07-24
36	35	2	1	33	Brad Paisley's 'Waitin on a Woman' ranks 33rd in the 2000s country charts. From the album Time Well Wasted, it's a touching ode to patience.	2025-07-24
37	36	2	1	34	Feel the romance with 'Then' by Brad Paisley, hitting the 34th spot in the 2000s country genre. It's from the album American Saturday Night!	2025-07-24
38	37	2	1	35	Celebrate the 35th-ranked 'American Saturday Night' by Brad Paisley. This 2000s country anthem, from the album of the same name, is pure fun!	2025-07-24
39	38	2	1	36	Quench your thirst for great music with 'Water' by Brad Paisley, ranked 36th in the 2000s country scene. From American Saturday Night, it's refreshing!	2025-07-24
40	39	2	1	37	Step into the future with Brad Paisley's 'Welcome to the Future', the 37th-ranked track in the 2000s country genre, from American Saturday Night.	2025-07-24
41	40	2	1	38	Discover the 38th-ranked 'Anything Like Me' by Brad Paisley. This 2000s country gem from Hits Alive is a playful nod to youthful antics.	2025-07-24
42	41	2	1	39	Explore the world with Brad Paisley's 'The World', ranking 39th in the 2000s country charts. From Time Well Wasted, it's a global journey!	2025-07-24
43	42	2	1	40	Start a band with Brad Paisley's 'Start a Band', the 40th-ranked hit from the 2000s country genre. From the album Play, it's a musical invitation!	2025-07-24
44	43	2	1	41	Ranked 41 in the 2000s, 'Remind Me' by Brad Paisley from the album 'This Is Country Music' is a country gem that'll stick in your mind!	2025-07-24
45	44	2	1	42	Get ready for a chuckle with 'I'm Gonna Miss Her (The Fishin' Song)' by Brad Paisley, ranked 42 in the 2000s, from the album 'Part II'.	2025-07-24
46	45	2	1	43	Did you know 'Celebrity' by Brad Paisley, ranked 43 in the 2000s, comes from the album 'Mud On The Tires'? A country hit with a twist!	2025-07-24
47	46	2	1	44	Brad Paisley's 'Little Moments', ranked 44 in the 2000s, also from 'Mud On The Tires', captures the sweet side of country life.	2025-07-24
48	47	2	1	45	Starting at rank 45 in the 2000s, 'Me Neither' by Brad Paisley from 'Who Needs Pictures' is a playful country tune you'll love.	2025-07-24
49	48	3	1	1	Kicking off the 2000s pop charts at number 1, Beyonce's 'Crazy In Love' from the album Dangerously In Love set the decade ablaze!	2025-07-24
50	49	3	1	2	At number 2, Kelly Clarkson's 'Since U Been Gone' from Breakaway rocked the 2000s pop scene with its empowering vibe.	2025-07-24
51	50	3	1	3	Did you know? Outkast's 'Hey Ya' from Speakerboxxx/The Love Below clinched the 3rd spot in the 2000s pop rankings!	2025-07-24
53	52	3	1	5	Usher's 'Yeah' from Confessions (Expanded Edition) grooves its way to number 5 in the 2000s pop charts, unforgettable!	2025-07-24
54	53	3	1	6	Feel the energy with Black Eyed Peas' 'I Gotta Feeling' from THE E.N.D. (THE ENERGY NEVER DIES), hitting number 6 in 2000s pop.	2025-07-24
55	54	3	1	7	Beyonce strikes again at number 7 with 'Single Ladies (Put a Ring on It)' from I AM...SASHA FIERCE, a 2000s pop anthem.	2025-07-24
56	55	3	1	8	Lady Gaga's 'Poker Face' from The Fame poker-faced its way to the 8th spot in the 2000s pop rankings, iconic!	2025-07-24
57	56	3	1	9	Rihanna's 'Umbrella' from Good Girl Gone Bad sheltered at number 9 in the 2000s pop charts, a stormy hit.	2025-07-24
58	57	3	1	10	Gwen Stefani's 'Hollaback Girl' from Love. Angel. Music. Baby. (Deluxe Version) hollered to the 10th spot in 2000s pop, fierce!	2025-07-24
59	58	3	1	11	Dive into the 2000s with Britney Spears' 'Toxic', ranked 11th, a pop sensation from the album In The Zone that'll get you hooked!	2025-07-24
60	59	3	1	12	Feel the power of Beyonce's 'Irreplaceable', a pop anthem from the 2000s, ranking at 12, featured on the album B'Day.	2025-07-24
61	60	3	1	13	Get low with Flo Rida's 'Low', a catchy pop hit from the 2000s, ranking 13th, and found on the album Mail on Sunday.	2025-07-24
62	61	3	1	14	Experience the emotional depth of Leona Lewis's 'Bleeding Love', a pop ballad from the 2000s, ranking 14th, from the album Spirit.	2025-07-24
63	62	3	1	15	Boom into the 2000s with Black Eyed Peas' 'Boom Boom Pow', a pop explosion ranking 15th, from THE E.N.D. (THE ENERGY NEVER DIES).	2025-07-24
64	63	3	1	16	Indulge in the sweet sounds of 50 Cent's 'Candy Shop', a pop track from the 2000s, ranking 16th, on the album The Massacre.	2025-07-24
65	64	3	1	17	Dance the night away with Lady Gaga's 'Just Dance', a pop hit from the 2000s, ranking 17th, featured on The Fame album.	2025-07-24
66	65	3	1	18	Savor the flavor of Lil Wayne's 'Lollipop', a pop delight from the 2000s, ranking 18th, from Tha Carter III (MTV Bonus Version).	2025-07-24
67	66	3	1	19	Enter the world of Rihanna's 'Disturbia', a pop thriller from the 2000s, ranking 19th, on the album Good Girl Gone Bad: Reloaded.	2025-07-24
68	67	3	1	20	Turn up the heat with Nelly's 'Hot in Herre', a pop classic from the 2000s, ranking 20th, from the album Nellyville.	2025-07-24
69	68	3	1	21	Ranked 21 in the 2000s, 'Baby Boy' by Beyonce from the album Dangerously In Love is a pop gem that'll make you dance!	2025-07-24
70	69	3	1	22	Feel the beat with 'In Da Club' by 50 Cent, hitting rank 22 in the 2000s pop charts, from the album Get Rich Or Die Tryin'.	2025-07-24
71	70	3	1	23	Ignite your spirit with 'Firework' by Katy Perry, soaring to rank 23 in the 2000s, from the album Teenage Dream.	2025-07-24
72	71	3	1	24	Did you know 'Tik Tok' by Kesha, from the album TiK-Tok - Remixes, rocked the 2000s pop scene at rank 24?	2025-07-24
73	72	3	1	25	Experience the drama of 'Bad Romance' by Lady Gaga, a 2000s pop hit at rank 25, from The Fame Monster (Deluxe Edition).	2025-07-24
74	73	3	1	26	Get ready to explode with 'Dynamite' by Taio Cruz, a pop sensation from the 2000s, ranking 26, from the album Rokstarr.	2025-07-24
75	74	3	1	27	Katy Perry's 'I Kissed A Girl' from One Of The Boys, a playful pop tune, reached rank 27 in the 2000s.	2025-07-24
76	75	3	1	28	Fall in love with 'Love Story' by Taylor Swift, a romantic pop ballad from Fearless (Taylor's Version), ranking 28 in the 2000s.	2025-07-24
77	76	3	1	29	You'll feel like you belong with 'You Belong With Me' by Taylor Swift, a 2000s pop hit at rank 29, from Fearless (Taylor's Version).	2025-07-24
78	77	3	1	30	Celebrate the urban vibe of 'Empire State of Mind' by Jay-Z, ranking 30 in the 2000s pop charts, from The Blueprint 3.	2025-07-24
79	78	3	1	31	Ranked 31 in the 2000s, Shakira's 'Hips Don't Lie' from the album Oral Fixation, Vol. 2 (Expanded Edition) is a pop sensation that got everyone moving!	2025-07-24
80	79	3	1	32	Justin Timberlake's 'SexyBack' stormed the charts at number 32 in the 2000s, a pop anthem from FutureSex/LoveSounds that redefined cool.	2025-07-24
81	80	3	1	33	Did you know 'Promiscuous' by Nelly Furtado hit rank 33 in the 2000s? This pop hit from the album Loose was all over the radio!	2025-07-24
82	81	3	1	34	Sean Paul's 'Temperature' soared to number 34 in the 2000s, a fiery pop track from The Trinity that heated up dance floors everywhere.	2025-07-24
83	82	3	1	35	Avril Lavigne's 'Complicated' captured hearts at rank 35 in the 2000s, a pop gem from Let Go that spoke to a generation.	2025-07-24
84	83	3	1	36	Alicia Keys' 'Fallin'' touched souls, ranking 36 in the 2000s, a soulful pop ballad from Songs In A Minor that's timeless.	2025-07-24
85	84	3	1	37	Mary J. Blige's 'Family Affair' was a family reunion at rank 37 in the 2000s, a pop classic from No More Drama that brought us together.	2025-07-24
86	85	3	1	38	Outkast's 'Ms. Jackson' apologized its way to number 38 in the 2000s, a poignant pop track from Stankonia that resonated deeply.	2025-07-24
87	86	3	1	39	Snoop Dogg's 'Drop It Like It's Hot' burned up the charts at rank 39 in the 2000s, a cool pop hit from R&G (Rhythm & Gangsta): The Masterpiece.	2025-07-24
52	51	3	1	40	Kanye West's 'Gold Digger' dug its way to number 40 in the 2000s, a catchy pop tune from Late Registration that's pure gold.	2025-07-24
88	87	3	1	41	Dive into the 41st-ranked pop hit of the 2000s, 'Lose Yourself' by Eminem, from the album Curtain Call: The Hits (Deluxe Edition). It's a must-listen!	2025-07-24
89	88	3	1	42	Feel the energy with 'Without Me' by Eminem, ranking 42 in the 2000s pop charts, from The Eminem Show. It's a classic you can't miss!	2025-07-24
90	89	3	1	43	Did you know 'Clocks' by Coldplay, from A Rush of Blood to the Head, hit the 43rd spot in the 2000s pop genre? It's timeless!	2025-07-24
91	90	3	1	44	Experience the drama of 'Viva La Vida' by Coldplay, ranking 44 in the 2000s pop charts, from Viva La Vida or Death and All His Friends. Epic!	2025-07-24
92	91	3	1	45	Get ready to be moved by 'Chasing Cars' by Snow Patrol, the 45th-ranked pop song of the 2000s, from Eyes Open. It's pure emotion!	2025-07-24
93	92	3	1	46	Discover the life-saving anthem 'How to Save a Life' by The Fray, hitting 46 in the 2000s pop rankings, from How To Save A Life. Inspiring!	2025-07-24
94	93	4	1	1	Kicking off the 2000s rock scene at #1, 'How You Remind Me' by Nickelback from the album Silver Side Up rocks the charts!	2025-07-24
95	94	4	1	2	Dive into the drama of the 2000s with 'In the End' by Linkin Park, ranking #2, from the album Hybrid Theory (Bonus Edition).	2025-07-24
96	95	4	1	3	Did you know? 'Boulevard of Broken Dreams' by Green Day, from American Idiot (20th Anniversary Deluxe Edition), hit #3 in the 2000s rock genre!	2025-07-24
97	96	4	1	4	Feel the energy of 'Dani California' by Red Hot Chili Peppers, soaring to #4 in the 2000s, from the album Stadium Arcadium.	2025-07-24
98	97	4	1	5	Linkin Park strikes again with 'Numb' at #5, a 2000s rock anthem from the album Meteora.	2025-07-24
99	98	4	1	6	Green Day's 'American Idiot' not only rocked the 2000s at #6 but also defined a generation, from the album American Idiot.	2025-07-24
100	99	4	1	7	3 Doors Down's 'Kryptonite' powered its way to #7 in the 2000s rock charts, from the album The Better Life.	2025-07-24
101	100	4	1	8	Papa Roach's 'Last Resort' screamed to #8 in the 2000s, a rock classic from the album Infest.	2025-07-24
102	101	4	1	9	Red Hot Chili Peppers groove with 'By the Way' at #9, a 2000s hit from By the Way (Deluxe Edition).	2025-07-24
103	102	4	1	10	The White Stripes' 'Seven Nation Army' marches to #10, a 2000s rock staple from the album Elephant.	2025-07-24
104	103	4	1	11	Ranked 11th in the 2000s, 'Mr Brightside' by The Killers rocks from the album Hot Fuss, igniting stages with its infectious energy!	2025-07-24
105	104	4	1	12	At number 12, 'Drops of Jupiter (Tell Me)' by Train, from the album Drops Of Jupiter, soars through the 2000s rock scene.	2025-07-24
106	105	4	1	13	Did you know? 'Hanging by a Moment' by Lifehouse, ranked 13th, defined 2000s rock from the album No Name Face.	2025-07-24
107	106	4	1	14	Feel the pulse of the 2000s with 'The Middle' by Jimmy Eat World, hitting rank 14, straight from Bleed American!	2025-07-24
108	107	4	1	15	Drama unfolds with 'I Write Sins Not Tragedies' by Panic! at the Disco, securing 15th spot, from A Fever You Can't Sweat Out.	2025-07-24
109	108	4	1	16	Crank up 'Feel Good Inc' by Gorillaz, a 16th ranker in the 2000s rock genre, from the album Demon Days.	2025-07-24
110	109	4	1	17	The Killers strike again with 'Somebody Told Me', ranking 17th, rocking out from the album Hot Fuss in the 2000s.	2025-07-24
111	110	4	1	18	Embrace the raw energy of 'When I'm Gone' by 3 Doors Down, at 18th place, from Away From The Sun in the 2000s rock era.	2025-07-24
112	111	4	1	19	Dare to groove with 'Dare' by Gorillaz, clinching the 19th spot, a 2000s rock hit from Demon Days.	2025-07-24
113	112	4	1	20	Everlong by Foo Fighters, ranked 20th, remains a timeless 2000s rock anthem from The Colour And The Shape.	2025-07-24
114	113	4	1	21	Dive into the 2000s rock scene with 'Best of You' by Foo Fighters, ranked 21, from the album In Your Honor!	2025-07-24
115	89	4	1	22	Feel the pulse of the 2000s with 'Clocks' by Coldplay, hitting rank 22, from the album A Rush of Blood to the Head.	2025-07-24
116	114	4	1	23	Experience the healing power of 'Fix You' by Coldplay, a 2000s rock gem at rank 23, from the album X&Y.	2025-07-24
117	90	4	1	24	Celebrate life with 'Viva La Vida' by Coldplay, a vibrant 2000s rock track at rank 24, from the album Viva La Vida or Death and All His Friends.	2025-07-24
118	115	4	1	25	Bask in the glow of 'Yellow' by Coldplay, a mellow 2000s rock classic at rank 25, from the album Parachutes.	2025-07-24
119	116	4	1	26	Discover the reason behind the hit 'The Reason' by Hoobastank, a 2000s rock anthem at rank 26, from the album The Reason (20th Anniversary).	2025-07-24
120	117	4	1	27	Get electrified with 'Numb/Encore' by Linkin Park, a dynamic 2000s rock mash-up at rank 27, from the album Numb / Encore: MTV Ultimate Mash-Ups Presents Collision Course.	2025-07-24
121	118	4	1	28	Embrace the haunting beauty of 'My Immortal' by Evanescence, a 2000s rock ballad at rank 28, from the album Fallen.	2025-07-24
122	119	4	1	29	Let 'Bring Me to Life' by Evanescence awaken your senses, a powerful 2000s rock track at rank 29, from the album Fallen.	2025-07-24
123	82	4	1	30	Unravel the complexities of 'Complicated' by Avril Lavigne, a catchy 2000s rock tune at rank 30, from the album Let Go.	2025-07-24
124	120	4	1	31	Dive into the 2000s rock scene with 'Sk8er Boi' by Avril Lavigne, ranked 31, from the album Let Go. It's a playful anthem that defined a generation!	2025-07-24
125	121	4	1	32	Feel the emotional depth of 'I'm With You', ranked 32, a rock ballad by Avril Lavigne from the album Let Go. It's a dramatic journey through the 2000s.	2025-07-24
126	122	4	1	33	Did you know 'Here Without You' by 3 Doors Down, ranked 33, from the album Away From The Sun, was a rock hit in the 2000s? Trivia time!	2025-07-24
127	123	4	1	34	Experience the intensity of 'The Pretender', ranked 34, a rock masterpiece by Foo Fighters from the album Echoes, Silence, Patience & Grace. It's a thrilling ride!	2025-07-24
128	124	4	1	35	Get ready for 'Chop Suey!' by System of a Down, ranked 35, a rock explosion from the album Toxicity. It's a wild trip through the 2000s!	2025-07-24
129	125	4	1	36	Unleash the power of 'Toxicity', ranked 36, another rock gem by System of a Down from the album Toxicity. It's a dramatic showcase of the 2000s!	2025-07-24
130	126	4	1	37	Rock out with 'BYOB' by System of a Down, ranked 37, from the album Mezmerize. It's a playful yet powerful statement from the 2000s!	2025-07-24
131	127	4	1	38	Feel the melancholy of 'Lonely Day', ranked 38, a rock ballad by System of a Down from the album Hypnotize. It's a dramatic reflection of the 2000s.	2025-07-24
132	128	4	1	39	Dance to the beat of 'Take Me Out' by Franz Ferdinand, ranked 39, a rock hit from the album Franz Ferdinand. It's a playful invitation to the 2000s!	2025-07-24
133	129	4	1	40	Explore the indie rock vibes of 'Maps' by Yeah Yeah Yeahs, ranked 40, from the album Fever To Tell (Deluxe Remastered). It's a trivia-worthy track from the 2000s!	2025-07-24
134	130	4	1	41	Ranked 41 in the 2000s, 'Float On' by Modest Mouse rocks from the album Good News For People Who Love Bad News. It's a must-listen!	2025-07-24
135	131	4	1	42	At number 42, Maroon 5's 'Harder to Breathe' from the 2000s rock scene, featured on Songs About Jane: 10th Anniversary Edition, hits hard.	2025-07-24
136	132	5	1	2	Did you know? 'ill be there for you' by The Rembrandts, also from L.P., secured the #2 spot among 2000s TV Themes.	2025-07-25
137	133	5	1	3	Climbing to #3, 'where everybody knows your name' by Gary Portnoy from the album Keeper, is a cherished tune in the 2000s TV Themes genre.	2025-07-25
138	134	5	1	4	At #4, 'the fresh prince of belair' by DJ Jazzy Jeff and The Fresh Prince from Greatest Hits, brings the 2000s TV Themes to life!	2025-07-25
139	135	5	1	5	Securing the #5 spot, 'the golden girls' by Andrew Gold from Movie Soundtrack - Songs from Film & Tv, is a heartwarming 2000s TV theme.	2025-07-25
140	136	5	1	6	Ranked #6, 'the jeffersons' by Janet DuBois from Movin' On Up (From "The Jeffersons") [Piano Version], adds soul to the 2000s TV Themes.	2025-07-25
141	137	5	1	7	At #7, 'the brady bunch' by The Brady Bunch from It's A Sunshine Day : The Best Of The Brady Bunch, captures the essence of 2000s TV Themes.	2025-07-25
142	138	5	1	8	Coming in at #8, 'the munsters' by Jack Marshall from The Munsters (Original Motion Picture Soundtrack), is a spooky hit in the 2000s TV Themes.	2025-07-25
143	139	5	1	9	Ranked #9, 'the beverly hillbillies' by Flatt and Scruggs from Town and Country, is a country classic among 2000s TV Themes.	2025-07-25
144	140	5	1	10	At #10, 'the andy griffith show' by Earle Hagen from Themes And Laughs From The Andy Griffith Show, rounds out the top 2000s TV Themes.	2025-07-25
145	141	5	1	11	Dive into the eerie vibes of the 2000s with 'The Twilight Zone' by Marius Constant, ranked 11, from the album 'Pops Out Of This World', a classic in TV Themes!	2025-07-25
146	142	5	1	12	Feel the thrill of the 2000s with 'Hawaii Five-O' by The Ventures, hitting rank 12, straight from the album 'Hawaii Five-O', a staple in TV Themes.	2025-07-25
147	143	5	1	13	Embark on a secret mission with 'Mission Impossible' by Lalo Schifrin, securing rank 13 in the 2000s, from the album 'More Mission: Impossible', a TV Themes gem.	2025-07-25
148	144	5	1	14	Step back into the cool 2000s with 'Peter Gunn' by Henry Mancini, clinching rank 14, from the album 'Music From Peter Gunn', a must-hear in TV Themes.	2025-07-25
149	145	5	1	15	Get ready for some classic 2000s action with 'Dragnet' by Walter Schumann, ranking at 15, from the album 'Best Film-Noir Music of the 1950s, Vol.1 (Remastered 2024)', a TV Themes legend.	2025-07-25
150	146	5	1	16	Slip into the suave 2000s with 'The Pink Panther Theme' by Henry Mancini, at rank 16, from the album 'The Pink Panther - Original Soundtrack', a TV Themes icon.	2025-07-25
151	147	5	1	17	Unleash your inner superhero with the 'Batman Theme' by Neal Hefti, soaring to rank 17 in the 2000s, from the album 'The Music Of DC Comics: Vol. 2', a TV Themes classic.	2025-07-25
152	148	5	1	18	Explore the final frontier with 'Star Trek' by Alexander Courage, reaching rank 18 in the 2000s, from the album 'The Ultimate Star Trek', a TV Themes staple.	2025-07-25
153	149	5	1	19	Laugh along with the 2000s hit 'The Simpsons' by Danny Elfman, at rank 19, from the album 'The City of Prague Philharmonic Orchestra Plays The Music Of Danny Elfman', a TV Themes favorite.	2025-07-25
154	150	5	1	20	Delve into the mysterious 2000s with 'X-Files' by Mark Snow, at rank 20, from the album 'X Files - I Want To Believe / OST', a haunting TV Themes track.	2025-07-25
155	151	5	1	21	Dive into the 2000s with 'Law and Order' by Mike Post, ranked 21st in TV Themes, from the album 'Inventions From The Blue Line'. It's drama at its finest!	2025-07-25
156	152	5	1	22	Feel the thrill of the 2000s with 'CSI: Crime Scene Investigation' by The Who, hitting rank 22 in TV Themes, from the album 'Who's Next (Deluxe Edition)'.	2025-07-25
157	153	5	1	23	Get a taste of the 2000s with 'The Sopranos' theme by Alabama 3, securing rank 23 in TV Themes, from the album 'The Wimmin from W.O.M.B.L.E, Vol. 2'.	2025-07-25
158	154	5	1	24	Step into the political drama of the 2000s with 'The West Wing' by W.G. Snuffy Walden, ranked 24th in TV Themes, from the album 'The West Wing (Original Television Soundtrack)'.	2025-07-25
159	155	5	1	25	Experience the urgency of the 2000s with 'ER' by James Newton Howard, clinching rank 25 in TV Themes, from the album 'Fantastic Beasts and Where to Find Them (Original Motion Picture Soundtrack)'.	2025-07-25
160	156	5	1	26	Catch the cool vibes of the 2000s with 'The O.C.' by Phantom Planet, landing at rank 26 in TV Themes, from the album 'The Guest (Expanded Edition)'.	2025-07-25
161	157	5	1	27	Laugh through the 2000s with 'Scrubs' by Lazlo Bane, humorously ranked 27th in TV Themes, from the album 'Scrubs'.	2025-07-25
162	158	5	1	28	Enter the quirky world of the 2000s with 'The Office' by The Scrantones, humorously ranked 28th in TV Themes, from the album 'The Office (Dashiin Remix)'.	2025-07-25
163	159	5	1	29	Get lost in the mystery of the 2000s with 'Lost' by Michael Giacchino, mysteriously ranked 29th in TV Themes, from the album 'Lost: The Final Season (Original Television Soundtrack)'.	2025-07-25
164	160	5	1	30	Diagnose the beats of the 2000s with 'House' by Massive Attack, clinically ranked 30th in TV Themes, from the album 'Лучшие хиты: Trip Hop'.	2025-07-25
165	161	5	1	31	Dive into the 31st ranked TV theme of the 2000s, 'Desperate Housewives' by Danny Elfman, from the album Desperate Housewives (TV Soundtrack). It's a genre-defining tune!	2025-07-25
166	162	5	1	32	Feel the tension with the 32nd ranked '24' theme by Sean Callery from the 2000s, featured on the album 24: The Game. A thrilling TV Themes classic!	2025-07-25
167	163	5	1	33	Explore the gritty sound of 'The Wire', ranked 33rd in the 2000s TV Themes, performed by Tom Waits from the album ...and all the pieces matter, Five Years of Music from The Wire (deluxe version).	2025-07-25
168	164	5	1	34	Unleash the drama with 'Breaking Bad', the 34th ranked track of the 2000s, composed by Dave Porter from the album Breaking Bad: Original Score from the Television Series. A must-hear in TV Themes!	2025-07-25
169	165	5	1	35	Step back in time with 'Mad Men', ranked 35th in the 2000s, brought to life by RJD2 from the album A Beautiful Mine (Mad Men Instrumental Theme) [From "Retrospective: The Music Of Mad M].	2025-07-25
170	166	5	1	36	Sink your teeth into 'True Blood', the 36th ranked TV theme of the 2000s, sung by Jace Everett from the album TRUE BLOOD (Music from the HBO® Original Series). A haunting melody!	2025-07-25
171	167	5	1	37	Get a taste of suspense with 'Dexter', ranked 37th in the 2000s TV Themes, crafted by Rolfe Kent from the album Dexter Season 4. It's chillingly good!	2025-07-25
172	168	5	1	38	Discover the quirky charm of 'Weeds', the 38th ranked track from the 2000s, sung by Malvina Reynolds from the album Weeds (Music from the Original Series). A unique TV theme!	2025-07-25
173	169	5	1	39	Experience the high life with 'Entourage', ranked 39th in the 2000s, composed by Mark Mothersbaugh from the album The Royal Tenenbaums (Original Soundtrack). A stylish TV theme!	2025-07-25
\.


--
-- Data for Name: decade_genre_trivia; Type: TABLE DATA; Schema: track_tables; Owner: postgres
--

COPY track_tables.decade_genre_trivia (id, decade_genre_id, trivia, trivia_mp3_url, created_at) FROM stdin;
\.


--
-- Data for Name: track; Type: TABLE DATA; Schema: track_tables; Owner: postgres
--

COPY track_tables.track (id, track_name, spotify_track_id, album_name, album_artwork, year_released, is_explicit, duration_ms, popularity, artist_id, featured_artist_id, artist_display_name, mode_flag, detail, created_at) FROM stdin;
1	cruise	0i5el041vd6nxrGEU8QRxy	Here's To The Good Times	https://i.scdn.co/image/ab67616d0000b273f5601676db551cb2a09e70a0	2012	f	208960	75	1	\N	Florida Georgia Line	GROUP	Now, let's dive into the story behind 'Cruise' by Florida Georgia Line. Did you know that this track was originally written by the duo's Tyler Hubbard and Brian Kelley in a small cabin in Georgia? They wanted to capture the feeling of freedom and the open road, and boy, did they nail it! 'Cruise' not only became a breakout hit but also set a record for the longest run at number one on the Country Airplay chart. And here's a fun fact: the song's infectious beat was inspired by a mix of hip-hop and country, showcasing the duo's innovative approach to music. Keep your radio locked right here, because we've got more great stories coming up!	2025-07-26 09:33:16.995758
2	die a happy man	5kNe7PE09d6Kvw5pAsx23n	Tangled Up	https://i.scdn.co/image/ab67616d0000b273f00a1acf866539632b187ea0	2015	f	227426	78	2	\N	Thomas Rhett	SOLO	Let's take a closer look at 'Die a Happy Man' by Thomas Rhett. This heartfelt ballad was penned by Thomas Rhett himself, along with Sean Douglas and Joe London, and it was inspired by his love for his wife, Lauren. The song's emotional depth struck a chord with listeners, soaring to the top of the charts and earning Thomas Rhett his first Grammy nomination. Did you know that the recording session was filled with laughter and tears, reflecting the song's genuine sentiment? And here's a little trivia for you: the song's beautiful piano intro was recorded in one take, adding to its raw and authentic feel. Stay tuned, because we're just getting started on this musical journey!	2025-07-26 09:33:16.995758
3	i hope you dance	65B1tEOv5W294uCKbmEcFV	I Hope You Dance	https://i.scdn.co/image/ab67616d0000b27363b3168c1970294e9ce5c415	2000	f	294533	66	3	\N	Lee Ann Womack	SOLO	Did you know that 'I Hope You Dance' was co-written by Tia Sillers and Mark D. Sanders in a Nashville coffee shop? The song's uplifting message resonated so deeply that it not only topped the country charts but also crossed over to pop, reaching number 14 on the Billboard Hot 100. Lee Ann Womack's heartfelt delivery was recorded in a single take, capturing the raw emotion that has touched millions. And remember, folks, keep dancing through life, because you never know what's around the corner!	2025-07-24 14:17:46.910223
4	where were you when the world stopped turning	4aOQG9TYcZOhT3sngkMI9K	Drive	https://i.scdn.co/image/ab67616d0000b273c5d5d983f8d9edc7f695cc72	2002	f	305093	58	4	\N	Alan Jackson	SOLO	Alan Jackson penned 'Where Were You When the World Stopped Turning' in the wake of 9/11, capturing the nation's grief and resilience. Recorded in a single day at the Sound Station studio in Nashville, the song's poignant lyrics struck a chord, earning Jackson a standing ovation at the CMA Awards. It's a testament to the power of music to heal and unite us in times of tragedy. Keep those memories close, and let's keep moving forward together, my friends.	2025-07-24 14:17:46.910223
5	amazed	6qc34bnVOyqGDPni8H5W0U	Lonely Grill	https://i.scdn.co/image/ab67616d0000b27341d35bfbac1ba0af6180206f	1999	f	240866	74	5	\N	Lonestar	GROUP	Lonestar's 'Amazed' was a labor of love, crafted by songwriters Marv Green, Aimee Mayo, and Chris Lindsey. The band recorded it in a cozy studio in Nashville, where they experimented with lush harmonies and a sweeping orchestral arrangement. The song not only topped the country charts but also became a crossover hit, reaching number one on the Billboard Hot 100. It's a reminder that love can truly amaze us, so keep those hearts open, folks!	2025-07-24 14:17:46.910223
6	courtesy of the red white and blue the angry american	0M7mWKqwTIaVjYyxfZmtTa	Unleashed	https://i.scdn.co/image/ab67616d0000b273bb5c54a68f9ce31f83b98de4	2002	f	195533	80	6	\N	Toby Keith	SOLO	Toby Keith's 'Courtesy of the Red, White and Blue (The Angry American)' was born from raw emotion following 9/11. Keith wrote it in a burst of patriotic fervor, and the song's bold lyrics stirred both controversy and admiration. Recorded in a Nashville studio, the track's intensity was captured in a single take. It became an anthem for many, reflecting the nation's complex feelings. And remember, folks, it's okay to feel and express those deep emotions.	2025-07-24 14:17:46.910223
7	its five oclock somewhere	7KysI43rsjlhjTeWO6ePUq	Greatest Hits Volume II	https://i.scdn.co/image/ab67616d0000b2734dba85eab31b275e997a12d4	2003	f	229800	74	4	\N	Alan Jackson and Jimmy Buffett	DUET	Alan Jackson and Jimmy Buffett teamed up for 'It's Five O'Clock Somewhere,' a song that became an instant classic. Written by Jim 'Moose' Brown and Don Rollins, the track was recorded in a relaxed session that captured the laid-back vibe perfectly. It topped the charts and became a summer anthem, reminding us all to take a break and enjoy life. So, next time you're feeling stressed, remember, it's always five o'clock somewhere!	2025-07-24 14:17:46.910223
8	redneck woman	26bL4gSULWDgdIMX0pRFrG	Here For The Party	https://i.scdn.co/image/ab67616d0000b273ddf15202c076358827b81302	2004	f	221333	68	8	\N	Gretchen Wilson	SOLO	Gretchen Wilson's 'Redneck Woman' was a game-changer, co-written by Wilson and John Rich. Recorded in a Nashville studio, the song's raw energy and unapologetic lyrics broke the mold, empowering women across the country. It soared to the top of the charts and became an anthem for authenticity. Wilson's fiery delivery was captured in a single take, adding to the song's gritty charm. Keep being yourself, folks, because that's what makes you special!	2025-07-24 14:17:46.910223
9	save a horse ride a cowboy	5s7m2xNZWgz5FqVSIvJcGA	Horse of a Different Color	https://i.scdn.co/image/ab67616d0000b273805374f00048ac081460cc70	2004	f	200306	75	9	\N	Big & Rich	SOLO	Big & Rich's 'Save a Horse (Ride a Cowboy)' was a wild ride from the start. Co-written by the duo and John Rich's brother, the song was recorded in a Nashville studio with a lively, party atmosphere. It became a crossover hit, blending country with rock and even a bit of hip-hop. The song's infectious energy and playful lyrics made it a favorite at parties everywhere. So, next time you're out, remember to save a horse and ride a cowboy!	2025-07-24 14:17:46.910223
10	suds in the bucket	6NhpIdjYoufuNNlBsgOztc	Restless	https://i.scdn.co/image/ab67616d0000b2739b6f689d6687f8930c154a86	2003	f	227266	70	10	\N	Sara Evans	SOLO	Sara Evans' 'Suds in the Bucket' was penned by Billy Montana and Tammy Wagoner, capturing the spirit of youthful rebellion. Recorded in a Nashville studio, the song's catchy melody and relatable lyrics struck a chord with listeners. It topped the country charts and became a summer anthem, reminding us of those carefree days. Evans' sweet vocals and the song's playful vibe make it a timeless classic. So, keep chasing those dreams, folks, no matter what anyone says!	2025-07-24 14:17:46.910223
11	when the sun goes down	5vLonpxn4VN0A8GtQOBSG0	When The Sun Goes Down	https://i.scdn.co/image/ab67616d0000b273528e4965b251e5f09dd32761	2004	f	290560	72	11	\N	Kenny Chesney and Uncle Kracker	DUET	Kenny Chesney and Uncle Kracker teamed up for 'When the Sun Goes Down,' a song that captured the essence of a perfect summer night. Written by Chesney and Brett James, the track was recorded in a relaxed session that mirrored its laid-back vibe. It topped the charts and became a staple at beach parties everywhere. The song's infectious melody and feel-good lyrics remind us to enjoy the simple moments in life. So, next time the sun goes down, take a moment to savor it!	2025-07-24 14:17:46.910223
12	live like you were dying	7B1QliUMZv7gSTUGAfMRRD	Live Like You Were Dying	https://i.scdn.co/image/ab67616d0000b273e6b859b16a880b851822871d	2004	f	300333	71	13	\N	Tim McGraw	SOLO	Tim McGraw's 'Live Like You Were Dying' was inspired by a friend's battle with illness, co-written by McGraw and Craig Wiseman. Recorded in a Nashville studio, the song's powerful message and McGraw's emotional delivery struck a chord with listeners. It topped the charts and won multiple awards, becoming an anthem for living life to the fullest. The song's impact reminds us to cherish every moment. So, keep living like you were dying, my friends, because every day is a gift!	2025-07-24 14:17:46.910223
13	im already there	34Vn9nKfztyLco9lJazy4j	I'm Already There	https://i.scdn.co/image/ab67616d0000b27315ea142bd41376087c24d6fe	2001	f	253373	60	5	\N	Lonestar	GROUP	Did you know that 'I'm Already There' was inspired by a real-life story of a band member missing his family while on tour? The songwriters, Gary Baker and Richie McDonald, crafted this heartfelt tune in a cozy Nashville studio, surrounded by family photos for inspiration. It soared to the top of the charts, becoming a beacon of hope for families separated by distance. And here's a fun fact: the band recorded it with a live string section to capture that emotional swell. So, keep your loved ones close, and remember, you're never as far away as you think. And that's your long-distance dedication from me to you!	2025-07-24 14:17:46.910223
14	beer for my horses	7E2DqvnVtbIrFrL5X6YH9Q	Unleashed	https://i.scdn.co/image/ab67616d0000b273bb5c54a68f9ce31f83b98de4	2002	f	204000	75	6	\N	Toby Keith and Willie Nelson	DUET	Toby Keith teamed up with the legendary Willie Nelson to bring us 'Beer for My Horses', a song that's as fun as it is controversial. Did you know they filmed the music video in downtown Nashville, turning the streets into a wild west scene? The songwriters, Toby Keith and Scotty Emerick, drew inspiration from old western films, aiming to capture that rugged spirit. It climbed the charts, sparking debates and discussions across the country. And here's a little trivia: Toby and Willie had a blast on set, even sharing a few cold ones. So, saddle up and enjoy the ride, because that's the spirit of country music. Keep it tuned right here!	2025-07-24 14:17:46.910223
15	mayberry	04rZkq3ihHmGNfKPgBiTX1	Melt	https://i.scdn.co/image/ab67616d0000b2736f14b3d807c3aed1d73a7d6b	2002	f	272986	58	15	\N	Rascal Flatts	GROUP	Rascal Flatts took us back to simpler times with 'Mayberry', a song that resonates with anyone longing for the good old days. The songwriters, Arlos Smith and Rodney Clawson, crafted this nostalgic gem in a small, rustic studio, aiming to capture the essence of small-town America. It quickly became a fan favorite, climbing the charts and touching hearts. Fun fact: the band used real-life stories from their own childhoods to add authenticity. So, take a moment to appreciate the simple joys in life, and remember, sometimes the best things are right in your own backyard. And that's your trip down memory lane, courtesy of Rascal Flatts!	2025-07-24 14:17:46.910223
16	bless the broken road	4YjjNHtEsTX6Af4mCTupT5	Feels Like Today	https://i.scdn.co/image/ab67616d0000b273d1ca2ddde8ff17e3991de83d	2004	f	226680	74	15	\N	Rascal Flatts	GROUP	Rascal Flatts' 'Bless the Broken Road' is a testament to the journey of life and love. Did you know this song was originally recorded by the Nitty Gritty Dirt Band? The songwriters, Marcus Hummon, Bobby Boyd, and Jeff Hanna, poured their hearts into the lyrics, reflecting on life's twists and turns. Rascal Flatts' version soared to the top of the charts, becoming a wedding staple. And here's a fun fact: the band recorded it in a single take, capturing the raw emotion. So, embrace every step of your journey, because it leads you to where you're meant to be. And that's your heartfelt dedication from Rascal Flatts!	2025-07-24 14:17:46.910223
17	days go by	2jwaErbghhcia4JqUYWz3g	Be Here	https://i.scdn.co/image/ab67616d0000b273930122975ef092c853ed28ac	2002	f	224629	65	16	\N	Keith Urban	SOLO	Keith Urban's 'Days Go By' is a vibrant celebration of life's fleeting moments. Did you know that Keith wrote this song in a burst of inspiration while on a road trip? The song captures the essence of living in the moment, and it was recorded in a lively studio session with a full band. It quickly climbed the charts, resonating with fans who appreciate the joy of the present. And here's a fun fact: Keith played multiple instruments on the track, showcasing his versatility. So, take a moment to enjoy the day, because as Keith reminds us, they go by all too fast. Keep it locked right here for more great tunes!	2025-07-24 14:17:46.910223
18	somebody like you	0b9djfiuDIMw1zKH6gV74g	Golden Road	https://i.scdn.co/image/ab67616d0000b2736b884d4969e2438f5a83ed5b	2002	f	323040	74	16	\N	Keith Urban	SOLO	Keith Urban's 'Somebody Like You' is a love song that captured hearts worldwide. Did you know that Keith wrote this song with John Shanks, and they recorded it in a marathon session, fueled by coffee and passion? The song soared to the top of the charts, becoming a crossover hit. And here's a fun fact: Keith played the banjo on the track, adding a unique flavor. So, if you're searching for that special someone, remember, they might be closer than you think. And that's your love song dedication from Keith Urban, right here on the radio!	2025-07-24 14:17:46.910223
19	youll think of me	68Iw932AjRCDEPLIzpmOtF	Golden Road	https://i.scdn.co/image/ab67616d0000b2736b884d4969e2438f5a83ed5b	2004	f	293600	62	16	\N	Keith Urban	SOLO	Keith Urban's 'You'll Think of Me' is a poignant reflection on moving on. Did you know that Keith wrote this song after a personal breakup, pouring his emotions into every lyric? The song was recorded in a quiet studio, allowing the raw emotion to shine through. It climbed the charts, resonating with anyone who's ever had to say goodbye. And here's a fun fact: Keith played the guitar solo in one take, capturing the song's intensity. So, if you're going through a tough time, remember, it's okay to let go and move forward. And that's your heartfelt message from Keith Urban, right here on the airwaves!	2025-07-24 14:17:46.910223
20	im movin on	7gpuC3rLKkI7PoJcEnSIO6	Rascal Flatts	https://i.scdn.co/image/ab67616d0000b273f7cfbbae7af7a43957580b00	2000	f	242866	51	15	\N	Rascal Flatts	GROUP	Rascal Flatts' 'I'm Movin' On' is an anthem of resilience and hope. Did you know that the songwriters, D. Vincent Williams and Phillip White, drew inspiration from their own life experiences? The band recorded it in a Nashville studio, capturing the song's uplifting spirit. It quickly became a fan favorite, climbing the charts and inspiring listeners. And here's a fun fact: the band performed it live at the Grand Ole Opry, receiving a standing ovation. So, if you're facing challenges, remember, you have the strength to move on. And that's your uplifting message from Rascal Flatts, right here on the radio!	2025-07-24 14:17:46.910223
21	these days	5nWgEBtaRwVrCMjer1RtLm	Melt	https://i.scdn.co/image/ab67616d0000b2736f14b3d807c3aed1d73a7d6b	2002	f	254493	61	15	\N	Rascal Flatts	GROUP	Rascal Flatts' 'These Days' is a song that captures the essence of modern life. Did you know that the songwriters, Steve Robson, Jeffrey Steele, and Danny Wells, crafted this tune in a bustling Nashville studio? The song reflects on the fast pace of today's world, resonating with listeners everywhere. It climbed the charts, becoming a staple on country radio. And here's a fun fact: the band used a mix of traditional and modern instruments to create its unique sound. So, take a moment to appreciate the beauty of these days, because they're all we've got. And that's your modern-day dedication from Rascal Flatts!	2025-07-24 14:17:46.910223
22	fast cars and freedom	0CKba2KBPP9TFbh5Nf8i4P	Feels Like Today	https://i.scdn.co/image/ab67616d0000b273d1ca2ddde8ff17e3991de83d	2004	f	262186	66	15	\N	Rascal Flatts	GROUP	Rascal Flatts' 'Fast Cars and Freedom' is a song that celebrates the joys of youth and freedom. Did you know that the songwriters, Gary Levox, Wendell Mobley, and Neil Thrasher, drew inspiration from their own teenage memories? The band recorded it in a lively studio session, capturing the song's energetic spirit. It quickly became a fan favorite, climbing the charts and becoming a summer anthem. And here's a fun fact: the band used real car sounds in the recording to add authenticity. So, if you're feeling nostalgic, crank up the volume and let the memories take you back. And that's your summer soundtrack from Rascal Flatts, right here on the radio!	2025-07-24 14:17:46.910223
23	what hurts the most	4bVuIlGQBMWS7vIhcx8Ae4	Me And My Gang	https://i.scdn.co/image/ab67616d0000b273aa6b03f85a0f2cb16e88ec0c	2006	f	214106	74	15	\N	Rascal Flatts	GROUP	Now, let's dive into the heart of 'What Hurts the Most' by Rascal Flatts. This gem was penned by Jeffrey Steele and Steve Robson, originally for Mark Wills, but it found its true home with Rascal Flatts. Did you know that during the recording, the band aimed for a raw, emotional sound, which you can hear in those haunting vocals? The song climbed to the top of the charts, staying at number one on the Billboard Hot Country Songs for four weeks. It's a testament to the power of heartfelt songwriting. And remember, folks, keep those emotions close, because that's where the magic happens. Keep it locked right here!	2025-07-24 14:17:46.910223
24	my wish	6Gfmj0HbpvxTdW0sdlzTDU	Me And My Gang	https://i.scdn.co/image/ab67616d0000b273aa6b03f85a0f2cb16e88ec0c	2006	f	248280	68	15	\N	Rascal Flatts	GROUP	Let's take a moment to appreciate 'My Wish' by Rascal Flatts. This touching ballad was co-written by the legendary duo of Jeffrey Steele and Steve Robson, the same masterminds behind 'What Hurts the Most'. The song was inspired by Steele's own daughter, adding a personal touch that resonates with listeners. Recorded in the cozy confines of Ocean Way Nashville, the track features lush strings that elevate its emotional impact. It soared to number one on the country charts, a true testament to its universal appeal. And as always, keep your wishes close, and your radio closer. Stay tuned!	2025-07-24 14:17:46.910223
25	stand	3tDo6YZzIZlc5gRy31lvJD	Life Is A Highway: Refueled Duets	https://i.scdn.co/image/ab67616d0000b2735a42bd25f34b900afa225eeb	2007	f	210600	63	15	\N	Rascal Flatts	GROUP	Now, let's stand up for 'Stand' by Rascal Flatts. This uplifting anthem was crafted by the talented duo of Blair Daly and Danny Orton. The song was recorded at the iconic Starstruck Studios, where the band aimed to capture a sense of unity and strength. Did you know that 'Stand' was inspired by the resilience of everyday heroes? It's a powerful reminder of the impact one person can have. The track reached the top of the charts, staying at number one for two weeks. So, stand tall and proud, and keep your dial right here for more great music!	2025-07-24 14:17:46.910223
26	life is a highway	2Fs18NaCDuluPG1DHGw1XG	Me And My Gang	https://i.scdn.co/image/ab67616d0000b273aa6b03f85a0f2cb16e88ec0c	2006	f	276320	77	15	\N	Rascal Flatts	GROUP	Let's hit the road with 'Life Is a Highway' by Rascal Flatts. This energetic cover was originally penned by Tom Cochrane, but Rascal Flatts brought their own flair to it. Recorded at the legendary Sound Kitchen in Nashville, the band added a country twist that made it a hit. Did you know that the song was featured in the movie 'Cars', boosting its popularity? It raced to the top of the charts, staying at number one for four weeks. So, buckle up and enjoy the ride, and keep your radio tuned right here!	2025-07-24 14:17:46.910223
27	skin sarabeth	0NB8Y8TXV0UTUoq9XHuOIr	Feels Like Today	https://i.scdn.co/image/ab67616d0000b273d1ca2ddde8ff17e3991de83d	2005	f	261266	43	15	\N	Rascal Flatts	GROUP	Now, let's get under the skin of 'Skin (Sarabeth)' by Rascal Flatts. This poignant track was co-written by Doug Johnson and Sarah Buxton, inspired by a real-life story of courage. Recorded at the intimate Blackbird Studio, the song captures the raw emotion of its narrative. Did you know that the band chose to keep the production minimal to focus on the story? It's a testament to the power of storytelling in music. The song climbed to number two on the charts, touching hearts along the way. Keep those stories close, and your radio closer. Stay tuned!	2025-07-24 14:17:46.910223
28	shes everything	3dAgQFdruU8ufWc5GE05xC	Time Well Wasted	https://i.scdn.co/image/ab67616d0000b2734030bcd7ed0469896d86c3b2	2006	f	266920	68	18	\N	Brad Paisley	SOLO	Let's celebrate 'She's Everything' by Brad Paisley. This romantic tune was co-written by Paisley himself and Frank Rogers, his longtime collaborator. Recorded at the legendary Ocean Way Nashville, the song features Paisley's signature guitar work, adding a personal touch. Did you know that the song was inspired by Paisley's wife, Kimberly Williams-Paisley? It's a sweet ode to love that resonated with fans, reaching number one on the charts. So, cherish those special someones, and keep your radio locked right here!	2025-07-24 14:17:46.910223
29	whiskey lullaby	4BXkf6yww23Vdju7E1fUrn	Hits Alive	https://i.scdn.co/image/ab67616d0000b2736217585c07b7417999f03d92	2003	f	259453	66	18	\N	Brad Paisley and Alison Krauss	DUET	Now, let's pour one out for 'Whiskey Lullaby' by Brad Paisley featuring Alison Krauss. This haunting ballad was co-written by Bill Anderson and Jon Randall, telling a tragic tale of love and loss. Recorded at the iconic Sound Emporium, the song features Krauss's ethereal vocals, adding depth to the story. Did you know that the song won the CMA Song of the Year in 2005? It's a powerful reminder of the impact of storytelling in music. So, raise a glass to the storytellers, and keep your radio tuned right here!	2025-07-24 14:17:46.910223
30	mud on the tires	4AQWKGBWTR7fVuUKxi5sKE	Mud On The Tires	https://i.scdn.co/image/ab67616d0000b2737302ccf08d789304c55ee73e	2003	f	208266	71	18	\N	Brad Paisley	SOLO	Let's get down and dirty with 'Mud on the Tires' by Brad Paisley. This fun-loving track was co-written by Paisley and Chris DuBois, capturing the joy of simple pleasures. Recorded at the cozy Sound Kitchen, the song features lively instrumentation that gets you moving. Did you know that the song was inspired by Paisley's own experiences growing up in West Virginia? It's a celebration of life's little adventures. The track climbed to number one on the charts, a testament to its universal appeal. So, get your tires muddy, and keep your radio locked right here!	2025-07-24 14:17:46.910223
31	alcohol	5wKaxpvqXq95IaoAVPLgoi	Time Well Wasted	https://i.scdn.co/image/ab67616d0000b2734030bcd7ed0469896d86c3b2	2005	f	290933	57	18	\N	Brad Paisley	SOLO	Now, let's raise a toast to 'Alcohol' by Brad Paisley. This witty tune was co-written by Paisley and Kelley Lovelace, offering a humorous take on life's favorite beverage. Recorded at the legendary Ocean Way Nashville, the song features Paisley's clever lyrics and playful guitar work. Did you know that the song was inspired by a conversation Paisley had with a friend? It's a lighthearted look at a serious topic. The track climbed to number four on the charts, proving that laughter is the best medicine. So, enjoy responsibly, and keep your radio tuned right here!	2025-07-24 14:17:46.910223
32	ticks	736KP0gdltJQWPKk0wVL7l	5th Gear	https://i.scdn.co/image/ab67616d0000b2739df06e6e8206ad4bf66405bf	2007	f	273160	57	18	\N	Brad Paisley	SOLO	Let's get a little cheeky with 'Ticks' by Brad Paisley. This playful track was co-written by Paisley and Kelley Lovelace, offering a fun twist on a classic pickup line. Recorded at the cozy Sound Kitchen, the song features Paisley's signature humor and catchy melody. Did you know that the song was inspired by a real-life encounter Paisley had? It's a lighthearted take on romance that resonated with fans. The track climbed to number one on the charts, proving that a little humor goes a long way. So, keep those laughs coming, and your radio locked right here!	2025-07-24 14:17:46.910223
33	letter to me	7wqMZWYeBxJt0obQPnF5NX	5th Gear	https://i.scdn.co/image/ab67616d0000b2739df06e6e8206ad4bf66405bf	2007	f	280826	52	18	\N	Brad Paisley	SOLO	Now, let's dive into the heart of 'Letter to Me'. Brad Paisley penned this gem as a heartfelt note to his younger self, capturing the essence of life's lessons with a touch of humor and nostalgia. Recorded in Nashville's historic RCA Studio A, the song features the warm strum of Paisley's '63 Telecaster, adding a personal touch to every note. It soared to the top of the charts, becoming a fan favorite for its relatable lyrics and Paisley's signature storytelling. And remember, folks, it's never too late to send a letter to your younger self. Keep those memories alive, and keep spinning the hits!	2025-07-24 14:17:46.910223
34	online	77lC0N7M07wmeozHWjNKts	5th Gear	https://i.scdn.co/image/ab67616d0000b2739df06e6e8206ad4bf66405bf	2007	f	296013	47	18	\N	Brad Paisley	SOLO	Let's take a closer look at 'Online'. This track was a playful nod to the digital age, co-written by Paisley and his frequent collaborator, Chris DuBois. The recording session was filled with laughter as Paisley and his band experimented with quirky sound effects to mimic the internet's buzz. It quickly became a chart-topping hit, resonating with fans for its witty take on online personas. And don't forget, folks, in the world of Brad Paisley, even the internet can be a stage for a good ol' country song. Keep those dials tuned right here!	2025-07-24 14:17:46.910223
35	waitin on a woman	3uJggzf2q1lCOl8EiQHFvN	Time Well Wasted	https://i.scdn.co/image/ab67616d0000b2734030bcd7ed0469896d86c3b2	2008	f	272586	57	18	\N	Brad Paisley	SOLO	Now, let's explore the soul of 'Waitin' on a Woman'. This song was inspired by Paisley's own grandmother's advice, adding a deeply personal touch to the lyrics. Recorded in the cozy confines of The Castle Recording Studios, the track features the soothing sounds of a dobro, played by the legendary Rob Ickes. It climbed the charts, touching hearts with its timeless message of patience and love. And remember, folks, sometimes the best things in life are worth waiting for. Keep those hearts open and those radios on!	2025-07-24 14:17:46.910223
36	then	3XKbdb9GB6u3hsnUklQTav	American Saturday Night	https://i.scdn.co/image/ab67616d0000b273d2993421bef048e835974055	2009	f	321640	63	18	\N	Brad Paisley	SOLO	Let's delve into the magic of 'Then'. This romantic ballad was crafted by Paisley and DuBois, capturing the journey of love through life's seasons. Recorded at Blackbird Studios, the song's lush orchestration, featuring the Nashville String Machine, adds a cinematic quality to every note. It soared to the top of the charts, becoming a wedding favorite for its heartfelt lyrics. And remember, folks, love is a journey that's always worth the ride. Keep those love songs playing and those hearts beating!	2025-07-24 14:17:46.910223
37	american saturday night	7xJqaCgeteqWPogqjjxkBl	American Saturday Night	https://i.scdn.co/image/ab67616d0000b273d2993421bef048e835974055	2009	f	274200	55	18	\N	Brad Paisley	SOLO	Now, let's celebrate the spirit of 'American Saturday Night'. This track was a joyous ode to multiculturalism, co-written by Paisley and DuBois. Recorded at The Castle, the song's lively tempo and vibrant instrumentation, including a spirited accordion, reflect the melting pot of American culture. It quickly became a fan favorite, resonating with listeners for its inclusive message. And remember, folks, every night can be an American Saturday night. Keep those celebrations going and those radios on!	2025-07-24 14:17:46.910223
38	water	5z1T8M153gyxX6IKJemYX7	American Saturday Night	https://i.scdn.co/image/ab67616d0000b273d2993421bef048e835974055	2009	f	261920	58	18	\N	Brad Paisley	SOLO	Let's dive into the refreshing vibes of 'Water'. This track was inspired by Paisley's love for fishing, adding a fun twist to the lyrics. Recorded at Blackbird Studios, the song features the soothing sounds of a steel guitar, played by the talented Brent Mason. It climbed the charts, becoming a summer anthem for its laid-back feel. And remember, folks, sometimes all you need is a little water to wash away the day's worries. Keep those fishing rods ready and those radios tuned!	2025-07-24 14:17:46.910223
39	welcome to the future	2qfGMqnRjiE4opZ4cBT65F	American Saturday Night	https://i.scdn.co/image/ab67616d0000b273d2993421bef048e835974055	2009	f	351453	42	18	\N	Brad Paisley	SOLO	Now, let's explore the futuristic sounds of 'Welcome to the Future'. This track was a bold look at technological advancements, co-written by Paisley and DuBois. Recorded at The Castle, the song's innovative production, featuring electronic beats and futuristic sound effects, set it apart from traditional country tunes. It quickly became a chart-topping hit, resonating with fans for its forward-thinking lyrics. And remember, folks, the future is always just around the corner. Keep those minds open and those radios on!	2025-07-24 14:17:46.910223
40	anything like me	74mZKvZcZzzvbOnt8NfWda	Hits Alive	https://i.scdn.co/image/ab67616d0000b2736217585c07b7417999f03d92	2009	f	268186	47	18	\N	Brad Paisley	SOLO	Let's take a fun ride with 'Anything Like Me'. This track was inspired by Paisley's own childhood antics, adding a humorous touch to the lyrics. Recorded at Blackbird Studios, the song's playful tempo and lively instrumentation, including a spirited banjo, reflect the joy of youthful mischief. It climbed the charts, becoming a fan favorite for its relatable storytelling. And remember, folks, a little mischief can go a long way. Keep those laughs coming and those radios tuned!	2025-07-24 14:17:46.910223
41	the world	5JTCdbn2KE4vx1vt8HJ3pZ	Time Well Wasted	https://i.scdn.co/image/ab67616d0000b2734030bcd7ed0469896d86c3b2	2009	f	241653	49	18	\N	Brad Paisley	SOLO	Now, let's journey through the world with 'The World'. This track was a heartfelt tribute to global unity, co-written by Paisley and DuBois. Recorded at The Castle, the song's uplifting melody and powerful lyrics, featuring a stirring choir, reflect the beauty of our shared humanity. It quickly became a chart-topping hit, resonating with listeners for its universal message. And remember, folks, the world is a big place, but we're all in it together. Keep those hearts open and those radios on!	2025-07-24 14:17:46.910223
42	start a band	0GneFCOVzvi6ok0oRC7Kfu	Play	https://i.scdn.co/image/ab67616d0000b273d8fe80b3b21b483c75afaa81	2008	f	324586	41	18	\N	Brad Paisley and Keith Urban	DUET	Let's rock out with 'Start a Band'. This track was a playful collaboration with Keith Urban, adding a fun twist to the lyrics. Recorded at Blackbird Studios, the song's energetic tempo and lively instrumentation, including dueling guitars, reflect the joy of musical partnership. It climbed the charts, becoming a fan favorite for its infectious energy. And remember, folks, sometimes all you need is a friend to start a band. Keep those guitars strumming and those radios tuned!	2025-07-24 14:17:46.910223
43	remind me	4ABua0yuWcpTotImEEJTaw	This Is Country Music	https://i.scdn.co/image/ab67616d0000b273e4ed191be04ba0e4253c77f4	2011	f	271906	61	18	\N	Brad Paisley and Carrie Underwood	DUET	Now, let's dive into the heart of 'Remind Me'. This gem was co-written by Brad Paisley and Chris DuBois, and it's a testament to the power of nostalgia in music. Recorded at The Castle Recording Studios, the song features a unique blend of Paisley's signature guitar work and the soulful vocals of Carrie Underwood. Did you know that the song's video was shot in black and white to emphasize the timeless feel of the lyrics? It's a beautiful reminder that some memories are worth revisiting. And that, my friends, is the magic of music, keeping us connected to the moments that matter. Keep those memories alive, and keep your radio tuned right here!	2025-07-24 14:17:46.910223
44	im gonna miss her the fishin song	4ipZsAA3YuqCDSXiPoEGIv	Part II	https://i.scdn.co/image/ab67616d0000b27394da46e08a9a9971436da68a	2001	f	194306	68	18	\N	Brad Paisley	SOLO	Alright, let's cast our lines into the story of 'I'm Gonna Miss Her (The Fishin' Song)'. This track was born from a playful conversation between Brad Paisley and his co-writer, Kelley Lovelace, about the age-old dilemma of love versus fishing. The song was recorded at The Castle Recording Studios, where Paisley's guitar twang perfectly captures the light-hearted spirit of the lyrics. Fun fact: the music video features Brad actually fishing, adding a touch of authenticity to the song's theme. It's a humorous take on priorities, and it's climbed the charts with the ease of a well-cast lure. So, keep your rods ready and your radio on, because you never know when the next big catch will come along!	2025-07-24 14:17:46.910223
45	celebrity	1Jmkm1iiVn6cxiKRaOlqOW	Mud On The Tires	https://i.scdn.co/image/ab67616d0000b2737302ccf08d789304c55ee73e	2003	f	223200	47	18	\N	Brad Paisley	SOLO	Let's roll out the red carpet for 'Celebrity'. This track was crafted by Brad Paisley alongside co-writers Chris DuBois and Kelley Lovelace, and it's a satirical look at fame. Recorded at The Castle Recording Studios, the song features a catchy beat that's as infectious as the fame it critiques. Did you know that the music video parodies various celebrities, adding a visual punch to the song's message? It's a clever commentary on the allure and absurdity of stardom. So, keep your eyes on the stars, but keep your feet on the ground, and stay tuned right here for more hits!	2025-07-24 14:17:46.910223
46	little moments	1hrCqasBFvB9IyLhrABVhc	Mud On The Tires	https://i.scdn.co/image/ab67616d0000b2737302ccf08d789304c55ee73e	2003	f	219266	54	18	\N	Brad Paisley	SOLO	Let's take a moment to appreciate 'Little Moments'. This heartfelt track was penned by Brad Paisley and Chris DuBois, and it's all about cherishing the small things in life. Recorded at The Castle Recording Studios, the song's gentle melody and Paisley's warm vocals create an intimate atmosphere. Fun fact: the song's video was filmed in a cozy home setting, emphasizing the personal nature of the lyrics. It's a reminder that sometimes, the little moments are the ones that mean the most. So, keep your heart open to those little joys, and keep your radio locked right here!	2025-07-24 14:17:46.910223
47	me neither	6A426nfNHDuTDs1uY0W0NF	Who Needs Pictures	https://i.scdn.co/image/ab67616d0000b273f8be6a6e73ff1219404c7a27	1999	f	200160	44	18	\N	Brad Paisley	SOLO	Let's tip our hats to 'Me Neither'. This witty track was co-written by Brad Paisley and Chris DuBois, and it's a playful take on shared dislikes. Recorded at The Castle Recording Studios, the song's clever lyrics and Paisley's smooth delivery make it a fun listen. Did you know that the song's video features Brad in various humorous situations, perfectly matching the song's light-hearted vibe? It's a reminder that sometimes, finding common ground can be as simple as agreeing on what you don't like. So, keep your sense of humor handy, and keep your radio tuned right here for more great tunes!	2025-07-24 14:17:46.910223
48	crazy in love	5IVuqXILoxVWvWEPm82Jxr	Dangerously In Love	https://i.scdn.co/image/ab67616d0000b27345680a4a57c97894490a01c1	2003	f	236133	82	21	\N	Beyoncé feat. Jay-Z	FEATURED	Now, let's dive into the magic behind 'Crazy in Love'. Did you know that the iconic horn riff was sampled from The Chi-Lites' 'Are You My Woman (Tell Me So)'? It was a last-minute addition that transformed the track into an instant classic. The song was co-written by Beyoncé, her future husband Jay-Z, and producer Rich Harrison. They recorded it in just two hours, capturing the raw energy that you can still feel today. And that, my friends, is the power of spontaneity in music. Keep it locked right here for more behind-the-scenes stories!	2025-07-24 17:33:36.12699
49	since u been gone	3xrn9i8zhNZsTtcoWgQEAd	Breakaway	https://i.scdn.co/image/ab67616d0000b27303dadde4d9d305c1c3e0d91c	2004	f	188960	79	23	\N	Kelly Clarkson	SOLO	Here's a fun fact about 'Since U Been Gone': it was originally offered to Pink, but she passed on it. Can you imagine? Kelly Clarkson's powerhouse vocals made it a smash hit, reaching the top of the charts in multiple countries. The song was penned by Max Martin and Dr. Luke, who crafted its infectious melody in a Swedish studio. Kelly recorded her vocals in just one take, showcasing her incredible talent and emotion. And that, my friends, is how a song can find its perfect voice. Stay tuned for more musical gems!	2025-07-24 17:33:36.12699
50	hey ya	2PpruBYCo4H7WOBJ7Q2EwM	Speakerboxxx/The Love Below	https://i.scdn.co/image/ab67616d0000b2736e88eb6508fd94cd1b745ce2	2003	f	235213	86	24	\N	OutKast	SOLO	Let's talk about 'Hey Ya!' by OutKast. This track was a solo effort by André 3000, who wrote and produced it in his bedroom studio. Did you know that the song's iconic 'shake it like a Polaroid picture' line was inspired by an actual Polaroid ad? The recording process was unique too, with André playing all the instruments himself. It became a cultural phenomenon, even inspiring a dance craze. And that, my friends, is how one man's vision can change the music world. Keep it right here for more fascinating stories!	2025-07-24 17:33:36.12699
52	yeah	5rb9QrpfcKFHM1EUbSIurX	Confessions (Expanded Edition)	https://i.scdn.co/image/ab67616d0000b273365b3fb800c19f7ff72602da	2004	f	250373	88	27	\N	Usher feat. Lil Jon & Ludacris	FEATURED	Let's dive into the story of 'Yeah!' by Usher. This track was a collaboration with Lil Jon and Ludacris, and it was recorded in just one day. The song's infectious beat was crafted by Lil Jon, who used a sample from an old-school funk track. Did you know that 'Yeah!' was originally intended for Petey Pablo? But Usher's smooth vocals made it a global sensation. And that, my friends, is how a last-minute decision can lead to a mega-hit. Keep it locked right here for more musical tales!	2025-07-24 17:33:36.12699
53	i gotta feeling	2H1047e0oMSj10dgp7p2VG	THE E.N.D. (THE ENERGY NEVER DIES)	https://i.scdn.co/image/ab67616d0000b273382514f0114ba8f4a16d5db4	2009	f	289133	81	29	\N	Black Eyed Peas	SOLO	Let's explore the magic behind 'I Gotta Feeling' by the Black Eyed Peas. This anthem was co-written by the group's own will.i.am, who drew inspiration from a night out in Las Vegas. The song's uplifting message was exactly what the world needed at the time. Did you know that it was recorded in multiple studios across the globe? The track's infectious beat and catchy lyrics made it a party staple. And that, my friends, is how a song can capture the spirit of celebration. Stay tuned for more musical journeys!	2025-07-24 17:33:36.12699
54	single ladies put a ring on it	2ZBNclC5wm4GtiWaeh0DMx	I AM...SASHA FIERCE	https://i.scdn.co/image/ab67616d0000b273e13de7b8662b085b0885ffef	2008	f	193213	68	21	\N	Beyoncé	SOLO	Let's uncover the story behind 'Single Ladies (Put a Ring on It)'. This empowering anthem was co-written by Beyoncé, The-Dream, and Tricky Stewart. The song's iconic choreography was inspired by Bob Fosse's 'Mexican Breakfast'. Did you know that the video was shot in just two days, with Beyoncé performing the dance routine over 60 times? The track's success was a testament to her dedication and vision. And that, my friends, is how a song can become a cultural phenomenon. Keep it locked right here for more behind-the-scenes stories!	2025-07-24 17:33:36.12699
55	poker face	5R8dQOPq8haW94K7mgERlO	The Fame	https://i.scdn.co/image/ab67616d0000b273613aaa3ae566d9f36008aed0	2008	f	237200	82	30	\N	Lady Gaga	SOLO	Let's delve into the story of 'Poker Face' by Lady Gaga. This track was inspired by her experiences in the underground club scene. Did you know that the song's catchy hook was originally about a different topic? Gaga changed it to make it more radio-friendly. The song was co-written with RedOne, who also produced it. They recorded it in a small studio in Los Angeles, capturing the raw energy that made it a global hit. And that, my friends, is how a song can evolve into a worldwide sensation. Stay tuned for more musical tales!	2025-07-24 17:33:36.12699
56	umbrella	2yPoXCs7BSIUrucMdK5PzV	Good Girl Gone Bad	https://i.scdn.co/image/ab67616d0000b273b9ff0a5f40d3406aed5e5e3b	2007	f	275986	77	31	\N	Rihanna feat. Jay-Z	FEATURED	Let's uncover the magic behind 'Umbrella' by Rihanna. This track was co-written by The-Dream and Tricky Stewart, who crafted its infectious beat in just a few hours. Did you know that the song was originally intended for Britney Spears? But Rihanna's powerful vocals made it a global sensation. The track's success was a testament to her unique style and the song's universal message. And that, my friends, is how a song can find its perfect voice. Keep it locked right here for more musical gems!	2025-07-24 17:33:36.12699
57	hollaback girl	0LzrhCZFXW94Y8nwtTuRlw	Love. Angel. Music. Baby. (Deluxe Version)	https://i.scdn.co/image/ab67616d0000b2737c7136a182372ccdffb3d3c4	2004	f	199853	75	32	\N	Gwen Stefani	SOLO	Let's dive into the story of 'Hollaback Girl' by Gwen Stefani. This track was co-written with Pharrell Williams, who produced it and added his signature sound. Did you know that the song's iconic cheerleader chant was inspired by Gwen's high school days? The track was recorded in Pharrell's home studio, capturing the playful energy that made it a hit. It became the first digital download to sell over a million copies. And that, my friends, is how a song can become a cultural phenomenon. Stay tuned for more musical journeys!	2025-07-24 17:33:36.12699
58	toxic	6I9VzXrHxO9rA9A5euc8Ak	In The Zone	https://i.scdn.co/image/ab67616d0000b273efc6988972cb04105f002cd4	2003	f	198800	87	33	\N	Britney Spears	SOLO	Did you know that 'Toxic' was originally offered to Kylie Minogue? That's right, folks! But it was Britney Spears who took this electrifying track to new heights, soaring to the top of the charts in over 20 countries. The song's infectious beat was crafted by Bloodshy & Avant, who drew inspiration from the sounds of French filter house music. And get this - the iconic video, featuring Britney in a daring array of costumes, was shot in just two days! Keep your radio locked right here, because we've got more amazing stories coming up!	2025-07-24 17:33:36.12699
59	irreplaceable	1G7DcLzPnopdZjLkev0K4e	B'Day	https://i.scdn.co/image/ab67616d0000b273632e4eafb2ffba59a2ae4500	2006	f	227666	73	21	\N	Beyoncé	SOLO	Here's a fun fact about 'Irreplaceable' - it was written in just two hours by Ne-Yo, originally intended for himself but handed over to the powerhouse that is Beyoncé. This track not only topped the Billboard Hot 100 for 10 weeks but also became an anthem for empowerment. The song's minimalist production, featuring just an acoustic guitar and a drum machine, showcases Beyoncé's vocal prowess. And guess what? It was recorded in her home studio! Stay tuned, because we're spinning more hits and sharing more stories, right here on your favorite station!	2025-07-24 17:33:36.12699
60	low	0CAfXk7DXMnon4gLudAp7J	Mail on Sunday	https://i.scdn.co/image/ab67616d0000b273f9bd7a6c772ac496015be3f8	2007	f	231400	87	34	\N	Flo Rida feat. T-Pain	FEATURED	Let me tell you something fascinating about 'Low' - it was the first song to sell over 3 million digital copies in the US! Flo Rida's collaboration with T-Pain was recorded in just one take, showcasing their incredible chemistry. The song's catchy hook was inspired by a conversation Flo Rida had with a friend about dancing at a club. And here's a fun tidbit - the 'apple bottom jeans' mentioned in the lyrics are a real brand! Keep it locked right here for more chart-topping hits and behind-the-scenes stories!	2025-07-24 17:33:36.12699
61	bleeding love	7wZUrN8oemZfsEd1CGkbXE	Spirit	https://i.scdn.co/image/ab67616d0000b27334fd9eb8cd48e518598aec55	2007	f	262466	79	36	\N	Leona Lewis	SOLO	You won't believe this, but 'Bleeding Love' was co-written by none other than OneRepublic's Ryan Tedder! Leona Lewis's powerhouse vocals took this song to the top of the charts in 35 countries. The song's emotional depth was inspired by Tedder's own experiences with heartbreak. And get this - the iconic music video was filmed in a single day in Los Angeles! Stick around, because we've got more incredible stories and hits coming your way!	2025-07-24 17:33:36.12699
62	boom boom pow	3opVsyWVYEAFK9bJAG8Opa	THE E.N.D. (THE ENERGY NEVER DIES)	https://i.scdn.co/image/ab67616d0000b273382514f0114ba8f4a16d5db4	2009	f	251440	72	29	\N	Black Eyed Peas	SOLO	Here's a cool fact about 'Boom Boom Pow' - it was the first song to top the Billboard Hot 100 chart based solely on digital downloads! The Black Eyed Peas' futuristic sound was crafted in their home studio, with will.i.am handling much of the production. The song's title was inspired by a comic book sound effect, adding to its unique vibe. And guess what? It was recorded in just three days! Keep your dial right here for more chart-topping stories and hits!	2025-07-24 17:33:36.12699
63	candy shop	5D2mYZuzcgjpchVY1pmTPh	The Massacre	https://i.scdn.co/image/ab67616d0000b27391f7222996c531b981e7bb3d	2005	f	209106	83	37	\N	50 Cent feat. Olivia	FEATURED	Did you know that 'Candy Shop' was produced by the legendary Scott Storch? That's right, folks! 50 Cent's collaboration with Olivia was recorded in Storch's Miami studio, where the iconic beat was crafted in just one session. The song's catchy hook was inspired by a conversation 50 Cent had about indulgence. And here's a fun fact - the 'candy shop' mentioned in the lyrics is a metaphor for a club! Stay tuned, because we've got more amazing stories and hits coming up!	2025-07-24 17:33:36.12699
64	just dance	2x7MyWybabEz6Y6wvHuwGE	The Fame	https://i.scdn.co/image/ab67616d0000b273613aaa3ae566d9f36008aed0	2008	f	241933	81	30	\N	Lady Gaga feat. Colby O'Donis	FEATURED	Here's something fascinating about 'Just Dance' - it was Lady Gaga's debut single, and it skyrocketed to the top of the charts in multiple countries! The song was co-written by Gaga and RedOne, who also produced the track. The infectious beat was inspired by a night out dancing, capturing the essence of letting loose. And get this - the iconic music video was filmed in just one day in Los Angeles! Keep your radio locked right here for more incredible stories and hits!	2025-07-24 17:33:36.12699
65	lollipop	1pm7lQGl6mvKWDxesZTVFp	Tha Carter III (MTV Bonus Version)	https://i.scdn.co/image/ab67616d0000b27302a999c3a283b5392e57737d	2008	f	299333	74	40	\N	Lil Wayne feat. Static Major	FEATURED	You won't believe this, but 'Lollipop' was recorded in just one take! Lil Wayne's collaboration with Static Major was an instant hit, topping the Billboard Hot 100 chart. The song's catchy hook was inspired by a conversation Wayne had about candy. And here's a fun fact - the 'lollipop' mentioned in the lyrics is a metaphor for something sweet! Stick around, because we've got more chart-topping stories and hits coming your way!	2025-07-24 17:33:36.12699
66	disturbia	2VOomzT6VavJOGBeySqaMc	Good Girl Gone Bad: Reloaded	https://i.scdn.co/image/ab67616d0000b273f9f27162ab1ed45b8d7a7e98	2008	f	238626	82	31	\N	Rihanna	SOLO	Did you know that 'Disturbia' was co-written by Chris Brown? That's right, folks! Rihanna's haunting track was inspired by a feeling of unease, capturing the essence of being in a disturbed state of mind. The song's eerie beat was crafted by the production team Stargate, who also worked on many of Rihanna's other hits. And get this - the iconic music video was filmed in just two days! Keep your dial right here for more incredible stories and hits!	2025-07-24 17:33:36.12699
67	hot in herre	04KTF78FFg8sOHC1BADqbY	Nellyville	https://i.scdn.co/image/ab67616d0000b273a8b9f97b9ea065b9a857e93f	2002	f	228240	81	42	\N	Nelly	SOLO	Here's a fun fact about 'Hot in Herre' - it was produced by The Neptunes, and the iconic beat was crafted in just one session! Nelly's track was inspired by a conversation he had about the heat in a club. The song's catchy hook became an instant hit, topping the Billboard Hot 100 chart. And guess what? It was recorded in Nelly's home studio! Stay tuned, because we've got more amazing stories and hits coming up!	2025-07-24 17:33:36.12699
68	baby boy	4WY3HyGXsWqjFRCVD6gnTe	Dangerously In Love	https://i.scdn.co/image/ab67616d0000b27345680a4a57c97894490a01c1	2003	f	244826	72	21	\N	Beyoncé feat. Sean Paul	FEATURED	Did you know that 'Baby Boy' was a collaboration that brought together the sultry sounds of Beyonce with the reggae vibes of Sean Paul? Recorded in Miami, this track was a labor of love, blending genres in a way that only a genius like producer Scott Storch could pull off. The song's infectious beat was crafted using a sample from the classic reggae tune 'Here Comes the Hotstepper' by Ini Kamoze. And here's a fun fact for you: during the recording sessions, Beyonce and Sean Paul had such a blast that they ended up improvising some of the lyrics on the spot! And that's the magic of music, folks, where spontaneity can lead to chart-topping hits. Keep it locked right here for more behind-the-scenes stories!	2025-07-24 17:33:36.12699
69	in da club	4RY96Asd9IefaL3X4LOLZ8	Get Rich Or Die Tryin'	https://i.scdn.co/image/ab67616d0000b273f7f74100d5cc850e01172cbf	2003	f	193466	77	37	\N	50 Cent	SOLO	Let's dive into the story behind 'In Da Club'. This track was the brainchild of Dr. Dre, who not only produced it but also helped 50 Cent craft those unforgettable lyrics. Recorded in the legendary Record One studio in Sherman Oaks, California, the song's iconic beat was inspired by a sample from 'It's Like That' by Run-DMC. Here's a little trivia for you: 50 Cent recorded his vocals in just one take, showcasing his raw talent and energy. And did you know that the song's success was so massive that it became a staple at every party and club across the nation? That's the power of a hit, my friends, and we'll be right back with more of those stories you love!	2025-07-24 17:33:36.12699
70	firework	4r6eNCsrZnQWJzzvFh4nlg	Teenage Dream	https://i.scdn.co/image/ab67616d0000b273d20c38f295039520d688a888	2010	f	227893	77	44	\N	Katy Perry	SOLO	Let's take a closer look at 'Firework' by Katy Perry. This uplifting anthem was co-written by Perry along with the talented duo of Mikkel S. Eriksen and Tor Erik Hermansen, better known as Stargate. The song's inspiring lyrics were born out of a desire to empower listeners, with Perry drawing from her own experiences of feeling like an outsider. Recorded in Los Angeles, the track features a soaring chorus that was crafted to make you feel like you can conquer the world. And here's a fun fact: the song's music video, directed by Dave Meyers, was inspired by the artwork of artist Dale Chihuly. So, keep your radio tuned right here for more stories that light up your day!	2025-07-24 17:33:36.12699
71	tik tok	5PSba04SiAEUe3q6PyaTpQ	TiK-Tok - Remixes	https://i.scdn.co/image/ab67616d0000b273233906d0f076db62a4f819d0	2009	f	200186	58	45	\N	Kesha	SOLO	Let's explore the story behind 'Tik Tok' by Kesha. This infectious track was penned by Kesha herself, along with the prolific songwriter Dr. Luke. The song's catchy beat was inspired by a sample from 'Don't Cha' by The Pussycat Dolls, giving it that irresistible dance vibe. Recorded in Los Angeles, 'Tik Tok' became an instant party anthem, with Kesha's playful lyrics and energetic delivery capturing the hearts of listeners everywhere. And here's a fun fact: Kesha recorded her vocals while brushing her teeth, adding to the song's quirky charm. So, keep it locked right here for more fun and fascinating stories from the world of music!	2025-07-24 17:33:36.12699
72	bad romance	0SiywuOBRcynK0uKGWdCnn	The Fame Monster (Deluxe Edition)	https://i.scdn.co/image/ab67616d0000b2735c9890c0456a3719eeecd8aa	2009	f	294573	88	30	\N	Lady Gaga	SOLO	Let's delve into the story behind 'Bad Romance' by Lady Gaga. This iconic track was co-written by Gaga and the talented RedOne, who also produced the song. Recorded in Los Angeles, 'Bad Romance' features a blend of electronic and pop elements that create its unique sound. The song's dramatic lyrics were inspired by Gaga's own experiences with love and relationships, adding a personal touch to the track. And here's a fun fact: the song's music video, directed by Francis Lawrence, became a cultural phenomenon, with its memorable scenes and choreography. So, keep your radio tuned right here for more stories that are as captivating as the music itself!	2025-07-24 17:33:36.12699
73	dynamite	1DqdF42leyFIzqNDv9CjId	Rokstarr	https://i.scdn.co/image/ab67616d0000b273a9006ae892a2255a865c0f7a	2009	f	203866	75	46	\N	Taio Cruz	SOLO	Let's take a closer look at 'Dynamite' by Taio Cruz. This upbeat track was written by Cruz himself, along with the talented Max Martin and Dr. Luke. Recorded in London, 'Dynamite' features a catchy beat that was crafted to get you moving. The song's lyrics were inspired by Cruz's desire to create a feel-good anthem, with its infectious chorus designed to lift your spirits. And here's a fun fact: the song's music video, directed by Alex Herron, was filmed in Los Angeles and features Cruz dancing through the streets. So, keep it locked right here for more stories that are as explosive as the music!	2025-07-24 17:33:36.12699
74	i kissed a girl	005lwxGU1tms6HGELIcUv9	One Of The Boys	https://i.scdn.co/image/ab67616d0000b273cd3978ebe35d93a07249b97f	2008	f	179640	74	44	\N	Katy Perry	SOLO	Let's explore the story behind 'I Kissed a Girl' by Katy Perry. This provocative track was co-written by Perry along with the talented duo of Max Martin and Dr. Luke. Recorded in Los Angeles, the song's bold lyrics were inspired by Perry's own experiences and her desire to push boundaries. The track features a catchy beat that was crafted to get stuck in your head, with its playful chorus adding to its appeal. And here's a fun fact: the song's music video, directed by Kinga Burza, was filmed in a colorful and whimsical setting, adding to the song's playful vibe. So, keep your radio tuned right here for more stories that are as bold and exciting as the music itself!	2025-07-24 17:33:36.12699
75	love story	6YvqWjhGD8mB5QXcbcUKtx	Fearless (Taylor's Version)	https://i.scdn.co/image/ab67616d0000b273a48964b5d9a3d6968ae3e0de	2008	f	235766	79	47	\N	Taylor Swift	SOLO	Let's dive into the story behind 'Love Story' by Taylor Swift. This romantic track was penned by Swift herself, drawing from her own experiences with love and heartbreak. Recorded in Nashville, 'Love Story' features a blend of country and pop elements that create its unique sound. The song's lyrics were inspired by classic literature, with Swift drawing parallels between her own life and the timeless tale of Romeo and Juliet. And here's a fun fact: the song's music video, directed by Trey Fanjoy, was filmed at a castle in Tennessee, adding to the song's fairy-tale charm. So, keep it locked right here for more stories that are as enchanting as the music!	2025-07-24 17:33:36.12699
76	you belong with me	1qrpoAMXodY6895hGKoUpA	Fearless (Taylor's Version)	https://i.scdn.co/image/ab67616d0000b273a48964b5d9a3d6968ae3e0de	2008	f	231124	85	47	\N	Taylor Swift	SOLO	Let's take a closer look at 'You Belong With Me' by Taylor Swift. This heartfelt track was written by Swift herself, drawing from her own experiences with unrequited love. Recorded in Nashville, the song features a blend of country and pop elements that create its unique sound. The lyrics were inspired by Swift's desire to connect with her audience, with the song's relatable story resonating with listeners everywhere. And here's a fun fact: the song's music video, directed by Roman White, was filmed at Swift's high school, adding a personal touch to the track. So, keep your radio tuned right here for more stories that are as touching as the music itself!	2025-07-24 17:33:36.12699
77	empire state of mind	2igwFfvr1OAGX9SKDCPBwO	The Blueprint 3	https://i.scdn.co/image/ab67616d0000b273fec1b815bb3c50a64a90fd10	2009	f	276920	86	22	\N	Jay-Z feat. Alicia Keys	FEATURED	Let's explore the story behind 'Empire State of Mind' by Jay-Z. This iconic track was co-written by Jay-Z and the talented Alicia Keys, who also provided the song's memorable hook. Recorded in New York City, 'Empire State of Mind' features a blend of hip-hop and R&B elements that create its unique sound. The song's lyrics were inspired by Jay-Z's love for his hometown, with the track serving as a tribute to the city that never sleeps. And here's a fun fact: the song's music video, directed by Hype Williams, was filmed in various iconic locations around New York, adding to the song's authenticity. So, keep it locked right here for more stories that are as vibrant as the music!	2025-07-24 17:33:36.12699
78	hips dont lie	3d0WouFnFmr0K3kjeza3fF	Oral Fixation, Vol. 2 (Expanded Edition)	https://i.scdn.co/image/ab67616d0000b27385432abc16fd92be0d435cb9	2005	f	220360	88	49	\N	Shakira feat. Wyclef Jean	FEATURED	Now, let's dive into the magic behind 'Hips Don't Lie'. This track was a collaboration with Wyclef Jean, who added his unique touch by incorporating a sample from his band's song 'Amores Como El Nuestro'. The recording sessions were filled with energy, with Shakira's dance moves inspiring the entire studio. Did you know that the song broke a record for the most radio spins in a single week? It's a testament to its infectious beat and Shakira's captivating performance. And remember, folks, keep those hips moving, because the music never lies!	2025-07-24 17:33:36.12699
79	sexyback	0O45fw2L5vsWpdsOdXwNAR	FutureSex/LoveSounds	https://i.scdn.co/image/ab67616d0000b273c6ba98fd3f3b396a6c6f7091	2006	f	242733	86	51	\N	Justin Timberlake feat. Timbaland	FEATURED	Let's take a peek behind the curtain of 'SexyBack'. Justin Timberlake teamed up with Timbaland, whose innovative production style gave the track its edgy sound. The song was recorded in a marathon session, with Justin and Timbaland pushing the boundaries of pop music. It debuted at number one on the Billboard Hot 100, a rare feat that showcased its instant impact. And here's a fun fact: the song's title was inspired by a conversation Justin had with a friend. So, keep it sexy, and keep it back, right here on the countdown!	2025-07-24 17:33:36.12699
80	promiscuous	2gam98EZKrF9XuOkU13ApN	Loose	https://i.scdn.co/image/ab67616d0000b273a6f439c8957170652f9410e2	2006	f	242293	89	53	\N	Nelly Furtado feat. Timbaland	FEATURED	Now, let's explore the story of 'Promiscuous'. Nelly Furtado and Timbaland's chemistry was electric, and their playful banter in the song was improvised during the recording. The track was a bold departure from Nelly's previous work, embracing a more urban sound. It topped the charts in multiple countries, proving its universal appeal. Did you know that the song's video was shot in a single day? It's a testament to the energy and creativity that went into this hit. So, keep it promiscuous, and keep it fun, right here on the airwaves!	2025-07-24 17:33:36.12699
81	temperature	0k2GOhqsrxDTAbFFSdNJjT	The Trinity	https://i.scdn.co/image/ab67616d0000b273d98221377ef3b1a7ad0a5d33	2005	f	216320	87	43	\N	Sean Paul	SOLO	Let's delve into the world of 'Temperature'. Sean Paul's signature dancehall style was on full display, with the song's infectious rhythm captivating listeners worldwide. The track was recorded in Jamaica, adding an authentic vibe to its sound. It reached the top of the Billboard Hot 100, marking a significant milestone for Sean Paul. And here's a fun fact: the song's title was inspired by the heat of the dance floor. So, turn up the temperature, and keep dancing, right here on the countdown!	2025-07-24 17:33:36.12699
83	fallin	0KQx6HOpJueiSkztcS0r7D	Songs In A Minor	https://i.scdn.co/image/ab67616d0000b2736d684b553a40e4a11e1db96d	2001	f	210200	80	48	\N	Alicia Keys	SOLO	Let's explore the magic of 'Fallin''. Alicia Keys wrote this song at the tender age of 14, showcasing her prodigious talent. The track was recorded in a single take, capturing the raw emotion of her performance. It topped the charts and won multiple Grammy Awards, cementing Alicia's place in music history. And here's a fun fact: the song's piano riff was inspired by a classical piece. So, keep falling for the music, and keep it soulful, right here on the countdown!	2025-07-24 17:33:36.12699
84	family affair	3aw9iWUQ3VrPQltgwvN9Xu	No More Drama	https://i.scdn.co/image/ab67616d0000b273096a7fc9668305db9d3175fc	2001	f	265866	83	55	\N	Mary J. Blige	SOLO	Now, let's dive into the story of 'Family Affair'. Mary J. Blige co-wrote this song with Dr. Dre, whose production added a hip-hop edge to her soulful sound. The track was recorded in a marathon session, with Mary's powerful vocals driving the energy. It topped the Billboard Hot 100, marking a significant milestone in her career. And here's a fun fact: the song's title was inspired by Mary's close-knit family. So, keep it in the family, and keep it real, right here on the airwaves!	2025-07-24 17:33:36.12699
85	ms jackson	0I3q5fE6wg7LIfHGngUTnV	Stankonia	https://i.scdn.co/image/ab67616d0000b2732350e31bc346a6c20e9de166	2000	f	270506	85	24	\N	OutKast	SOLO	Let's uncover the magic behind 'Ms. Jackson'. OutKast's André 3000 wrote this song as an apology to Erykah Badu's mother, adding a personal touch to the track. The song was recorded in a small studio, giving it an intimate feel. It topped the charts and won a Grammy, showcasing its universal appeal. And here's a fun fact: the song's title was inspired by a character from a TV show. So, keep it personal, and keep it funky, right here on the countdown!	2025-07-24 17:33:36.12699
86	drop it like its hot	2NBQmPrOEEjA8VbeWOQGxO	R&G (Rhythm & Gangsta): The Masterpiece	https://i.scdn.co/image/ab67616d0000b273e803716268c173c3f9a0c057	2004	f	266066	80	56	\N	Snoop Dogg feat. Pharrell Williams	FEATURED	Now, let's explore the story of 'Drop It Like It's Hot'. Snoop Dogg and Pharrell Williams collaborated on this track, with Pharrell's production giving it a unique sound. The song was recorded in a single day, capturing the spontaneity of their creative process. It topped the Billboard Hot 100, marking a significant milestone for Snoop. And here's a fun fact: the song's title was inspired by a phrase Snoop used in his daily life. So, keep dropping it like it's hot, and keep it cool, right here on the airwaves!	2025-07-24 17:33:36.12699
51	gold digger	1PS1QMdUqOal0ai3Gt7sDQ	Late Registration	https://i.scdn.co/image/ab67616d0000b273428d2255141c2119409a31b2	2005	f	207626	82	25	\N	Kanye West feat. Jamie Foxx	FEATURED	Let's delve into the world of 'Gold Digger'. Kanye West co-wrote this song with Jamie Foxx, whose soulful vocals added a unique flavor to the track. The song was recorded in a marathon session, with Kanye's energy driving the creative process. It topped the Billboard Hot 100 and won multiple awards, showcasing its impact. And here's a fun fact: the song's title was inspired by a phrase Kanye heard in his neighborhood. So, keep digging for gold, and keep it real, right here on the countdown!	2025-07-24 17:33:36.12699
87	lose yourself	5Z01UMMf7V1o0MzF86s6WJ	Curtain Call: The Hits (Deluxe Edition)	https://i.scdn.co/image/ab67616d0000b273eab40fc794b88b9d1e012578	2002	f	326466	80	58	\N	Eminem	SOLO	Did you know that 'Lose Yourself' was written in just three hours? Eminem penned this masterpiece while on the set of the movie '8 Mile', inspired by the intensity of the moment. The song's iconic beat was crafted by producer Jeff Bass, who used a sample from the movie's score. It became the first rap song to win an Academy Award for Best Original Song. And here's a fun fact: the original recording had a different third verse, but Eminem re-recorded it to perfection. Keep reaching for those dreams, and keep your radio locked right here!	2025-07-24 17:33:36.12699
88	without me	7lQ8MOhq6IN2w8EYcFNSUk	The Eminem Show	https://i.scdn.co/image/ab67616d0000b2736ca5c90113b30c3c43ffb8f4	2002	f	290320	89	58	\N	Eminem	SOLO	Let's dive into the fun side of 'Without Me'! Did you know that Eminem wrote this track as a playful response to critics and the media? The song's catchy hook was inspired by a sample from Labi Siffre's 'I Got The...', giving it that irresistible beat. And here's a behind-the-scenes tidbit: the music video, directed by Joseph Kahn, was shot in just two days and features Eminem in multiple outrageous personas. It's all about having fun and not taking life too seriously. Keep smiling, and stay tuned for more hits!	2025-07-24 17:33:36.12699
91	chasing cars	5hnyJvgoWiQUYZttV4wXy6	Eyes Open	https://i.scdn.co/image/ab67616d0000b2735da2756220da9b6f17924f8f	2006	f	267960	85	60	\N	Snow Patrol	SOLO	Let's delve into the heartfelt story of 'Chasing Cars'. Did you know that Gary Lightbody wrote this song in just 20 minutes? It was inspired by a moment of pure emotion, capturing the essence of longing and love. The song's minimalist production, featuring just piano and vocals, was recorded in a small studio in Belfast. And here's a fun fact: the song gained massive popularity after being featured in the TV show 'Grey's Anatomy'. It's a reminder that sometimes, the simplest things can touch our hearts the deepest. Keep chasing your dreams, and keep your radio locked right here!	2025-07-24 17:33:36.12699
92	how to save a life	5fVZC9GiM4e8vu99W0Xf6J	How To Save A Life	https://i.scdn.co/image/ab67616d0000b27359b8b957f164ce660919f1f4	2005	f	262533	87	61	\N	The Fray	SOLO	Let's uncover the touching story behind 'How to Save a Life'. Did you know that Isaac Slade wrote this song based on his experiences working with troubled teens? The lyrics reflect the struggles and hopes of those trying to make a difference. The song's emotional intensity was captured in a small studio in Denver, with just a piano and guitar. And here's a fun fact: the song's popularity soared after being featured in the TV show 'Grey's Anatomy', resonating with millions. It's a powerful reminder of the impact we can have on each other's lives. Keep making a difference, and stay tuned for more!	2025-07-24 17:33:36.12699
90	viva la vida	1mea3bSkSGXuIRvnydlB5b	Viva La Vida or Death and All His Friends	https://i.scdn.co/image/ab67616d0000b273e21cc1db05580b6f2d2a3b6e	2008	f	242373	91	59	\N	Coldplay	GROUP	Let's delve into the magic of 'Viva La Vida' by Coldplay. This track was a bold departure for the band, embracing a more orchestral sound inspired by historical figures and art. Recorded at the historic Church Studios, the song's strings were arranged by the talented Davide Rossi, adding a majestic flair. Did you know? The song's title, translating to 'Long Live Life,' reflects its uplifting message. And here's a fun fact: the iconic artwork was inspired by Frida Kahlo's self-portraits. Keep celebrating life, and stay tuned for more musical journeys!	2025-07-24 18:40:25.024139
93	how you remind me	0gmbgwZ8iqyMPmXefof8Yf	Silver Side Up	https://i.scdn.co/image/ab67616d0000b273699a422d25adc550dc5aa11c	2001	f	223840	88	62	\N	Nickelback	SOLO	Now, let's dive into the story behind 'How You Remind Me' by Nickelback. This track was penned by Chad Kroeger in a moment of personal reflection, capturing the essence of a relationship's ups and downs. Recorded in the iconic Greenhouse Studios in Vancouver, the song's production was a labor of love, with Kroeger and producer Rick Parashar meticulously crafting each note. Fun fact: the iconic guitar riff was inspired by a melody Chad hummed in the shower! And there you have it, folks, a song that not only topped the charts but also touched hearts worldwide. Keep those dials tuned right here!	2025-07-24 18:40:25.024139
94	in the end	60a0Rd6pjrkxjPbaKzXjfq	Hybrid Theory (Bonus Edition)	https://i.scdn.co/image/ab67616d0000b273e2f039481babe23658fc719a	2000	f	216880	92	63	\N	Linkin Park	GROUP	Let's take a closer look at 'In the End' by Linkin Park. This track was a collaborative effort between Mike Shinoda and Chester Bennington, born out of late-night sessions in their makeshift studio. The song's iconic piano riff was actually played by Shinoda, showcasing his versatility. Did you know that 'In the End' was one of the last songs recorded for the 'Hybrid Theory' album? It's a testament to perseverance and creativity. And remember, folks, no matter where life takes you, keep rocking with us here on the radio!	2025-07-24 18:40:25.024139
95	boulevard of broken dreams	0U87auHx1iZTEFcq9KVdmO	American Idiot (20th Anniversary Deluxe Edition)	https://i.scdn.co/image/ab67616d0000b2738214d54694cb9813927f7f3f	2004	f	260936	81	64	\N	Green Day	GROUP	Now, let's explore the magic behind 'Boulevard of Broken Dreams' by Green Day. Billie Joe Armstrong wrote this anthem during a solitary walk in New York City, channeling feelings of isolation and longing. The song was recorded in the legendary Ocean Way Recording studio in Hollywood, where the band experimented with a more stripped-down sound. Trivia time: the iconic guitar riff was inspired by The Beatles' 'Strawberry Fields Forever.' So, keep walking down that boulevard with us, and stay tuned for more hits!	2025-07-24 18:40:25.024139
96	dani california	10Nmj3JCNoMeBQ87uw5j8k	Stadium Arcadium	https://i.scdn.co/image/ab67616d0000b27309fd83d32aee93dceba78517	2006	f	282160	83	65	\N	Red Hot Chili Peppers	GROUP	Let's delve into the story of 'Dani California' by Red Hot Chili Peppers. This track was a collaborative effort between Anthony Kiedis and John Frusciante, inspired by a fictional character named Dani. The song was recorded at The Mansion in Los Angeles, a historic studio known for its eerie atmosphere. Did you know that the iconic bassline was crafted by Flea in just one take? It's a testament to the band's raw talent and energy. So, keep rocking with us, and we'll see you on the other side!	2025-07-24 18:40:25.024139
97	numb	2nLtzopw4rPReszdYBJU6h	Meteora	https://i.scdn.co/image/ab67616d0000b2735f1f51d14e8bea89484ecd1b	2003	f	187520	91	63	\N	Linkin Park	GROUP	Now, let's uncover the tale behind 'Numb' by Linkin Park. This powerful track was co-written by Mike Shinoda and Chester Bennington, reflecting on the pressures of conformity. Recorded at NRG Recording Studios in North Hollywood, the song's production was a blend of electronic and rock elements, showcasing the band's innovative sound. Fun fact: the iconic chorus was inspired by a poem Chester wrote in high school. So, keep feeling the music with us, and stay tuned for more!	2025-07-24 18:40:25.024139
98	american idiot	6nTiIhLmQ3FWhvrGafw2zj	American Idiot	https://i.scdn.co/image/ab67616d0000b27308a1b1e0674086d3f1995e1b	2004	f	176346	85	64	\N	Green Day	GROUP	Let's dive into the story of 'American Idiot' by Green Day. Billie Joe Armstrong penned this rebellious anthem as a critique of American society, capturing the zeitgeist of the early 2000s. Recorded at Ocean Way Recording in Hollywood, the song's production was a bold departure from the band's previous work. Did you know that the iconic guitar riff was inspired by The Kinks' 'All Day and All of the Night'? So, keep rocking out with us, and we'll see you on the flip side!	2025-07-24 18:40:25.024139
99	kryptonite	6ZOBP3NvffbU4SZcrnt1k6	The Better Life	https://i.scdn.co/image/ab67616d0000b2732868c4713a3912fd476b42f1	2000	f	233933	84	66	\N	3 Doors Down	SOLO	Now, let's explore the magic behind 'Kryptonite' by 3 Doors Down. This track was written by lead singer Brad Arnold in a moment of introspection, reflecting on the strength of friendship. Recorded at Ardent Studios in Memphis, the song's production was a blend of rock and alternative elements, showcasing the band's unique sound. Fun fact: the iconic chorus was inspired by a dream Brad had about Superman. So, keep flying high with us, and stay tuned for more hits!	2025-07-24 18:40:25.024139
100	last resort	5W8YXBz9MTIDyrpYaCg2Ky	Infest	https://i.scdn.co/image/ab67616d0000b273985bf5ede2fe4a048ee85f28	2000	f	199906	85	67	\N	Papa Roach	SOLO	Let's delve into the story of 'Last Resort' by Papa Roach. This powerful track was penned by Jacoby Shaddix during a dark period in his life, capturing the raw emotion of desperation. Recorded at Indigo Ranch Studios in Malibu, the song's production was a blend of nu-metal and punk influences, showcasing the band's intense energy. Did you know that the iconic scream in the chorus was recorded in one take? So, keep rocking out with us, and we'll see you on the other side!	2025-07-24 18:40:25.024139
101	by the way	1f2V8U1BiWaC9aJWmpOARe	By the Way (Deluxe Edition)	https://i.scdn.co/image/ab67616d0000b273de1af2785a83cc660155a0c4	2002	f	216933	81	65	\N	Red Hot Chili Peppers	GROUP	Now, let's uncover the tale behind 'By the Way' by Red Hot Chili Peppers. This track was a collaborative effort between Anthony Kiedis and John Frusciante, inspired by a chance encounter in Los Angeles. Recorded at Cello Studios in Hollywood, the song's production was a blend of funk and rock elements, showcasing the band's eclectic sound. Fun fact: the iconic bassline was crafted by Flea while jamming with a local street musician. So, keep grooving with us, and stay tuned for more!	2025-07-24 18:40:25.024139
102	seven nation army	3dPQuX8Gs42Y7b454ybpMR	Elephant	https://i.scdn.co/image/ab67616d0000b273a69f71a8794e2d867a52f98f	2003	f	232106	86	68	\N	The White Stripes	SOLO	Let's dive into the story of 'Seven Nation Army' by The White Stripes. This iconic track was written by Jack White in a moment of creative inspiration, capturing the raw energy of rock 'n' roll. Recorded at Toe Rag Studios in London, the song's production was a return to the band's minimalist roots. Did you know that the iconic riff was inspired by a malfunctioning semi-acoustic guitar? So, keep rocking out with us, and we'll see you on the flip side!	2025-07-24 18:40:25.024139
103	mr brightside	003vvx7Niy0yvhvHt4a68B	Hot Fuss	https://i.scdn.co/image/ab67616d0000b273ccdddd46119a4ff53eaf1f5d	2004	f	222973	91	69	\N	The Killers	GROUP	Now, let's dive into the story behind 'Mr. Brightside' by The Killers. Did you know that this track was inspired by a real-life heartbreak? Brandon Flowers penned the lyrics after suspecting his girlfriend of cheating. The song was recorded in a tiny studio in Las Vegas, where the band's raw energy was captured perfectly. 'Mr. Brightside' became a sleeper hit, slowly climbing the charts and eventually becoming one of the longest-charting songs in UK history. And here's a fun fact: the iconic guitar riff was almost left out of the final cut! Keep your dial locked right here, folks, as we keep the hits coming!	2025-07-24 18:40:25.024139
104	drops of jupiter tell me	2hKdd3qO7cWr2Jo0Bcs0MA	Drops Of Jupiter	https://i.scdn.co/image/ab67616d0000b273a65df73c4011b6a9357c89f0	2001	f	259933	84	70	\N	Train	SOLO	Alright, let's take a closer look at 'Drops of Jupiter (Tell Me)' by Train. This song was born from a deeply personal place, as lead singer Pat Monahan wrote it while coping with the loss of his mother. The lyrics are filled with celestial imagery, reflecting his journey through grief. The track was recorded in Sausalito, California, and features an eclectic mix of instruments, including a cello and a harmonica. It soared to the top of the charts, winning two Grammy Awards. And did you know that the song's title was inspired by a conversation Pat had with his mother in a dream? Stay tuned, music lovers, for more stories behind the hits!	2025-07-24 18:40:25.024139
105	hanging by a moment	0wqOReZDnrefefEsrIGeR4	No Name Face	https://i.scdn.co/image/ab67616d0000b273d0494f682c986764e0bc629c	2000	f	216066	72	71	\N	Lifehouse	SOLO	Let's explore the magic behind 'Hanging by a Moment' by Lifehouse. This song was a breakout hit for the band, and it was written by lead singer Jason Wade in just 10 minutes! The track was recorded in a small studio in Seattle, and its soaring chorus became an anthem for a generation. 'Hanging by a Moment' spent an impressive 20 weeks at the top of the Billboard Adult Top 40 chart. And here's a little trivia for you: the song's title was inspired by a line from a poem Jason read. Keep it right here, folks, as we continue our musical journey!	2025-07-24 18:40:25.024139
106	the middle	6GG73Jik4jUlQCkKg9JuGO	Bleed American	https://i.scdn.co/image/ab67616d0000b27395d1d98c5176e4f982bd73d6	2001	f	165853	85	72	\N	Jimmy Eat World	SOLO	Now, let's delve into the story of 'The Middle' by Jimmy Eat World. This song was a lifeline for many fans, offering hope and encouragement. It was written by the band's lead singer, Jim Adkins, who drew inspiration from his own teenage struggles. The track was recorded in a small studio in Tempe, Arizona, and its uplifting message resonated with listeners worldwide. 'The Middle' became a chart-topping hit and remains a staple at live shows. And did you know that the song's iconic guitar riff was created using a broken amp? Stay tuned, music lovers, for more behind-the-scenes stories!	2025-07-24 18:40:25.024139
107	i write sins not tragedies	4bPQs0PHn4xbipzdPfn6du	A Fever You Can't Sweat Out	https://i.scdn.co/image/ab67616d0000b2730a8881b0d247346c3c447bf3	2005	f	186634	77	73	\N	Panic! at the Disco	SOLO	Let's uncover the tale behind 'I Write Sins Not Tragedies' by Panic! at the Disco. This song was a bold statement from the band, blending punk and baroque pop elements. It was written by lead singer Brendon Urie and guitarist Ryan Ross, inspired by a wedding gone wrong. The track was recorded in a studio in Las Vegas, and its dramatic string section was arranged by a local orchestra. 'I Write Sins Not Tragedies' became a massive hit, reaching the top of the Billboard charts. And here's a fun fact: the song's music video was filmed in a single day! Keep your radio tuned right here for more fascinating stories!	2025-07-24 18:40:25.024139
108	feel good inc	0d28khcov6AiegSCpG5TuT	Demon Days	https://i.scdn.co/image/ab67616d0000b27319d85a472f328a6ed9b704cf	2005	f	222640	90	74	\N	Gorillaz	SOLO	Now, let's explore the story behind 'Feel Good Inc' by Gorillaz. This song was a groundbreaking collaboration between Damon Albarn and Jamie Hewlett, blending hip-hop and electronic music. It was recorded in London's Studio 13, and its infectious beat was inspired by Albarn's love for old-school hip-hop. 'Feel Good Inc' became a global hit, winning a Grammy Award for Best Pop Collaboration with Vocals. And did you know that the song's iconic windmill sound was created using a sample from a 1960s cartoon? Stay tuned, folks, for more intriguing tales from the world of music!	2025-07-24 18:40:25.024139
109	somebody told me	6PwjJ58I4t7Mae9xfZ9l9v	Hot Fuss	https://i.scdn.co/image/ab67616d0000b273ccdddd46119a4ff53eaf1f5d	2004	f	197200	84	69	\N	The Killers	GROUP	Let's dive into the story behind 'Somebody Told Me' by The Killers. This song was a breakout hit for the band, and it was written by Brandon Flowers after a night out in Las Vegas. The track was recorded in a small studio in the city, and its catchy chorus became an instant classic. 'Somebody Told Me' climbed the charts, becoming a staple on radio stations worldwide. And here's a fun fact: the song's iconic synth riff was inspired by a dream Brandon had! Keep your dial locked right here, music lovers, for more stories behind the hits!	2025-07-24 18:40:25.024139
110	when im gone	3WbphvawbMZ8FyqDxYGdSQ	Away From The Sun	https://i.scdn.co/image/ab67616d0000b27383c39b0d32eb4a2064e1e228	2002	f	260333	78	66	\N	3 Doors Down	SOLO	Now, let's take a closer look at 'When I'm Gone' by 3 Doors Down. This song was a heartfelt ballad, written by lead singer Brad Arnold after the loss of a friend. The track was recorded in a studio in Mississippi, and its emotional lyrics struck a chord with listeners. 'When I'm Gone' became a chart-topping hit, resonating with fans around the world. And did you know that the song's iconic guitar riff was inspired by a riff from a classic rock song? Stay tuned, folks, for more fascinating stories from the world of music!	2025-07-24 18:40:25.024139
111	dare	4Hff1IjRbLGeLgFgxvHflk	Demon Days	https://i.scdn.co/image/ab67616d0000b27319d85a472f328a6ed9b704cf	2005	f	244999	82	74	\N	Gorillaz	SOLO	Let's explore the magic behind 'Dare' by Gorillaz. This song was a bold experiment, blending hip-hop and electronic music. It was written by Damon Albarn and features vocals by Shaun Ryder of Happy Mondays. The track was recorded in London's Studio 13, and its infectious beat was inspired by Albarn's love for old-school hip-hop. 'Dare' became a global hit, reaching the top of the charts in several countries. And here's a fun fact: the song's iconic 'windmill' sound was created using a sample from a 1960s cartoon! Keep your radio tuned right here for more intriguing tales!	2025-07-24 18:40:25.024139
112	everlong	5UWwZ5lm5PKu6eKsHAGxOk	The Colour And The Shape	https://i.scdn.co/image/ab67616d0000b2730389027010b78a5e7dce426b	1997	f	250546	87	77	\N	Foo Fighters	GROUP	Now, let's delve into the story behind 'Everlong' by Foo Fighters. This song was a powerful anthem, written by Dave Grohl after a breakup. The track was recorded in a small studio in Virginia, and its raw energy captured the band's live sound perfectly. 'Everlong' became a chart-topping hit, resonating with fans around the world. And did you know that the song's iconic guitar riff was inspired by a riff from a classic rock song? Stay tuned, music lovers, for more behind-the-scenes stories!	2025-07-24 18:40:25.024139
113	best of you	5FZxsHWIvUsmSK1IAvm2pp	In Your Honor	https://i.scdn.co/image/ab67616d0000b2736c44679425e2695001b35d72	2005	f	255626	78	77	\N	Foo Fighters	GROUP	Now, let's dive into the heart of 'Best of You' by Foo Fighters. This track was born out of a deeply personal place for Dave Grohl, written in the wake of some tough times. It's a song about resilience and pushing through adversity, which really resonates with fans. Recorded at the legendary Studio 606, the song features some killer guitar work from Chris Shiflett, adding that extra punch. And here's a fun fact: during live performances, the crowd's energy often leads to an extended outro, turning it into a communal moment of release. Keep rockin', and remember, you're never alone in your struggles!	2025-07-24 18:40:25.024139
89	clocks	0BCPKOYdS2jbQ8iyB56Zns	A Rush of Blood to the Head	https://i.scdn.co/image/ab67616d0000b273de09e02aa7febf30b7c02d82	2002	f	307879	89	59	\N	Coldplay	GROUP	Let's take a closer look at 'Clocks' by Coldplay. This song was crafted in the band's unique creative space, where Chris Martin's piano riff became the heartbeat of the track. It's fascinating to know that the song was almost left off the album, but its infectious melody won over the band. Recorded at the famous Parr Street Studios, 'Clocks' showcases some innovative production techniques, blending electronic and organic sounds seamlessly. And did you know? The music video, shot in a single take, adds to its timeless appeal. Keep those clocks ticking, and stay tuned for more!	2025-07-24 18:40:25.024139
114	fix you	7LVHVU3tWfcxj5aiPFEW4Q	X&Y	https://i.scdn.co/image/ab67616d0000b2734e0362c225863f6ae2432651	2005	f	295533	89	59	\N	Coldplay	GROUP	Now, let's explore the story behind 'Fix You' by Coldplay. This song was inspired by Chris Martin's desire to comfort someone going through a tough time, making it a universal anthem of hope. Recorded at the legendary AIR Studios in London, the track features some beautiful orchestral arrangements, adding depth to its emotional core. Fun fact: the song's iconic organ riff was played on a vintage instrument, giving it that haunting quality. And here's a little behind-the-scenes drama: the band initially struggled with the song's structure, but perseverance paid off. Keep shining, and remember, we're all here to lift each other up!	2025-07-24 18:40:25.024139
115	yellow	3AJwUDP919kvQ9QcozQPxg	Parachutes	https://i.scdn.co/image/ab67616d0000b2739164bafe9aaa168d93f4816a	2000	f	266773	94	59	\N	Coldplay	GROUP	Now, let's uncover the story behind 'Yellow' by Coldplay. This song was born from a simple, yet powerful, moment when Chris Martin looked up at the stars and felt inspired. Recorded at the legendary Rockfield Studios, the track features some beautiful acoustic guitar work, adding to its intimate feel. Fun fact: the song's title was almost 'Yellow Car,' but the band chose the more poetic option. And did you know? The music video, shot on a beach, captures the song's serene vibe perfectly. Keep shining bright, and stay tuned for more!	2025-07-24 18:40:25.024139
116	the reason	5B5eTk7DF8KVp1zpQoY1XY	The Reason (20th Anniversary)	https://i.scdn.co/image/ab67616d0000b27394f8b5f85bad2c8affe6cc7d	2003	f	232800	85	78	\N	Hoobastank	SOLO	Let's dive into the heart of 'The Reason' by Hoobastank. This track was penned by lead singer Doug Robb, reflecting on personal growth and relationships. Recorded at the famous Bay 7 Studios, the song's emotional lyrics are complemented by some powerful guitar riffs, adding to its intensity. Fun fact: the song's music video was shot in one continuous take, adding to its raw energy. And did you know? 'The Reason' became a staple at weddings, symbolizing love and commitment. Keep searching for your reasons, and stay tuned for more!	2025-07-24 18:40:25.024139
117	numbencore	5sNESr6pQfIhL3krM8CtZn	Numb / Encore: MTV Ultimate Mash-Ups Presents Collision Course	https://i.scdn.co/image/ab67616d0000b2737282412ad025c14f7039f516	2004	f	205733	80	63	\N	Linkin Park feat. Jay-Z	GROUP	Now, let's explore the unique story behind 'Numb/Encore' by Linkin Park and Jay-Z. This track was born from an unlikely collaboration, blending rock and hip-hop in a groundbreaking way. Recorded at the legendary NRG Recording Studios, the song features some killer production work from Mike Shinoda, adding to its dynamic energy. Fun fact: the song's music video, directed by Kimo Proudfoot, showcases a futuristic theme, reflecting its innovative sound. And did you know? 'Numb/Encore' won a Grammy for Best Rap/Sung Collaboration, cementing its place in music history. Keep pushing boundaries, and stay tuned for more!	2025-07-24 18:40:25.024139
118	my immortal	4UzVcXufOhGUwF56HT7b8M	Fallen	https://i.scdn.co/image/ab67616d0000b27325f49ab23f0ec6332efef432	2003	f	262533	78	79	\N	Evanescence	SOLO	Let's take a closer look at 'My Immortal' by Evanescence. This song was written by Amy Lee and Ben Moody, inspired by personal loss and grief. Recorded at the famous Ocean Studios, the track features some haunting piano work, adding to its emotional depth. Fun fact: the song's music video, shot in black and white, captures its somber mood perfectly. And did you know? 'My Immortal' was initially written as an instrumental piece, but Amy's powerful vocals transformed it into a timeless ballad. Keep cherishing your memories, and stay tuned for more!	2025-07-24 18:40:25.024139
119	bring me to life	0COqiPhxzoWICwFCS4eZcp	Fallen	https://i.scdn.co/image/ab67616d0000b27325f49ab23f0ec6332efef432	2003	f	235893	90	79	\N	Evanescence	SOLO	Now, let's delve into the story behind 'Bring Me to Life' by Evanescence. This track was born from a moment of creative tension, blending rock and electronic elements in a unique way. Recorded at the legendary NRG Recording Studios, the song features some powerful vocals from Amy Lee, adding to its intensity. Fun fact: the song's iconic bridge, featuring guest vocals by Paul McCoy, was added at the last minute, giving it that extra punch. And did you know? 'Bring Me to Life' became a defining anthem for the nu-metal genre, resonating with fans worldwide. Keep bringing your dreams to life, and stay tuned for more!	2025-07-24 18:40:25.024139
82	complicated	5xEM5hIgJ1jjgcEBfpkt2F	Let Go	https://i.scdn.co/image/ab67616d0000b273f7ec724fbf97a30869d06240	2002	f	244506	86	54	\N	Avril Lavigne	SOLO	Let's explore the magic behind 'Complicated' by Avril Lavigne. This song was crafted by Avril and her team, reflecting on the complexities of teenage life. Recorded at the famous 2nd Street Studio, the track features some catchy guitar riffs, adding to its youthful energy. Fun fact: the song's music video, shot in a mall, captures the song's relatable theme perfectly. And did you know? 'Complicated' became a defining hit for Avril, launching her into pop-punk stardom. Keep embracing life's complexities, and stay tuned for more!	2025-07-24 18:40:25.024139
120	sk8er boi	00Mb3DuaIH1kjrwOku9CGU	Let Go	https://i.scdn.co/image/ab67616d0000b273f7ec724fbf97a30869d06240	2002	f	204000	82	54	\N	Avril Lavigne	SOLO	Now, let's dive into the story behind 'Sk8er Boi'. This track was penned by Avril Lavigne and her guitarist Evan Taubenfeld during a spontaneous jam session in the studio. The song's catchy riff was inspired by a melody Evan was playing around with, and Avril quickly crafted the lyrics around it. 'Sk8er Boi' not only topped the charts but also became a cultural phenomenon, sparking debates about class and romance. It was recorded in just a few takes, capturing the raw energy that made it an instant classic. And remember, folks, keep your ears open for those hidden gems in every song!	2025-07-24 18:40:25.024139
121	im with you	1jlG3KJ3gdYmhfuySFfpO1	Let Go	https://i.scdn.co/image/ab67616d0000b273f7ec724fbf97a30869d06240	2002	f	223066	80	54	\N	Avril Lavigne	SOLO	Let's take a closer look at 'I'm With You'. This heartfelt ballad was written by Avril Lavigne, Scott Spock, and Lauren Christy. The song was inspired by Avril's feelings of loneliness while on tour, and it was recorded in a small, intimate studio setting to capture that emotional rawness. 'I'm With You' climbed the charts, resonating with listeners worldwide, and even earned a Grammy nomination. The song's piano intro was a last-minute addition, adding a touch of melancholy that perfectly complements Avril's soulful vocals. Keep those tissues handy, because this one's a tear-jerker!	2025-07-24 18:40:25.024139
122	here without you	3NLrRZoMF0Lx6zTlYqeIo4	Away From The Sun	https://i.scdn.co/image/ab67616d0000b27383c39b0d32eb4a2064e1e228	2002	f	238733	82	66	\N	3 Doors Down	SOLO	Now, let's explore the story behind 'Here Without You'. This poignant track was crafted by 3 Doors Down's Brad Arnold, who wrote the lyrics in just 15 minutes while missing his family on tour. The song was recorded in a barn studio, giving it a unique, rustic sound. 'Here Without You' soared to the top of the charts, becoming an anthem for those separated from loved ones. The band's producer, Rick Parashar, added subtle orchestral elements to enhance the song's emotional depth. So, next time you're feeling a bit lonely, let this song be your comforting companion!	2025-07-24 18:40:25.024139
123	the pretender	7x8dCjCr0x6x2lXKujYD34	Echoes, Silence, Patience & Grace	https://i.scdn.co/image/ab67616d0000b27383e260c313dc1ff1f17909cf	2007	f	269373	81	77	\N	Foo Fighters	GROUP	Let's delve into the creation of 'The Pretender'. This powerhouse track was written by Foo Fighters' Dave Grohl, who drew inspiration from his frustration with the music industry. The song was recorded in Studio 606, and its intense energy was captured in a single take, showcasing the band's raw talent. 'The Pretender' not only topped the charts but also became a rallying cry for authenticity in music. The song's iconic drum intro was a last-minute addition, adding to its explosive impact. Keep rocking, and never stop being true to yourself!	2025-07-24 18:40:25.024139
124	chop suey	2DlHlPMa4M17kufBvI2lEN	Toxicity	https://i.scdn.co/image/ab67616d0000b27307bc7d2a745636c356b4d0aa	2001	f	210240	88	80	\N	System of a Down	SOLO	Now, let's uncover the story behind 'Chop Suey!'. This explosive track was penned by System of a Down's Serj Tankian and Daron Malakian, inspired by Daron's personal struggles. The song was recorded in a marathon session at Hollywood's Cello Studios, capturing the band's intense energy. 'Chop Suey!' not only became a chart-topping hit but also sparked controversy due to its provocative lyrics. The song's unique blend of heavy guitars and Middle Eastern influences set it apart. So, keep your ears open for those unexpected musical twists!	2025-07-24 18:40:25.024139
125	toxicity	0snQkGI5qnAmohLE7jTsTn	Toxicity	https://i.scdn.co/image/ab67616d0000b27307bc7d2a745636c356b4d0aa	2001	f	218933	87	80	\N	System of a Down	SOLO	Let's explore the creation of 'Toxicity'. This hard-hitting track was written by System of a Down's Serj Tankian and Daron Malakian, inspired by the chaos of Los Angeles. The song was recorded in a frenzy at Hollywood's Cello Studios, capturing the band's raw energy. 'Toxicity' not only topped the charts but also became an anthem for those feeling overwhelmed by societal pressures. The song's iconic bassline was a last-minute addition, adding to its intense impact. So, next time you're feeling the pressure, let this song be your release!	2025-07-24 18:40:25.024139
126	byob	0EYOdF5FCkgOJJla8DI2Md	Mezmerize	https://i.scdn.co/image/ab67616d0000b273c65f8d04502eeddbdd61fa71	2005	f	255466	82	80	\N	System of a Down	SOLO	Now, let's dive into the story behind 'B.Y.O.B.'. This politically charged track was penned by System of a Down's Daron Malakian and Serj Tankian, inspired by the Iraq War. The song was recorded in a heated session at Hollywood's Cello Studios, capturing the band's fiery energy. 'B.Y.O.B.' not only became a chart-topping hit but also sparked debates about war and politics. The song's unique blend of heavy guitars and jazz influences set it apart. So, keep your ears open for those unexpected musical twists!	2025-07-24 18:40:25.024139
127	lonely day	1VNWaY3uNfoeWqb5U8x2QX	Hypnotize	https://i.scdn.co/image/ab67616d0000b273f5e7b2e5adaa87430a3eccff	2005	f	167906	84	80	\N	System of a Down	SOLO	Let's take a closer look at 'Lonely Day'. This melancholic track was written by System of a Down's Serj Tankian and Daron Malakian, inspired by feelings of isolation. The song was recorded in a serene session at Hollywood's Cello Studios, capturing the band's emotional depth. 'Lonely Day' not only resonated with listeners worldwide but also became a soothing balm for those feeling alone. The song's haunting piano intro was a last-minute addition, adding to its emotional impact. So, next time you're feeling a bit lonely, let this song be your comforting companion!	2025-07-24 18:40:25.024139
128	take me out	20I8RduZC2PWMWTDCZuuAN	Franz Ferdinand	https://i.scdn.co/image/ab67616d0000b27309a90531b85be7899c3234c4	2004	f	237026	87	81	\N	Franz Ferdinand	SOLO	Now, let's explore the story behind 'Take Me Out'. This infectious track was penned by Franz Ferdinand's Alex Kapranos and Nick McCarthy, inspired by a game of pool. The song was recorded in a lively session at Glasgow's Rockfield Studios, capturing the band's energetic vibe. 'Take Me Out' not only topped the charts but also became a dance floor favorite. The song's iconic guitar riff was a last-minute addition, adding to its irresistible charm. So, next time you're out, let this song take you away!	2025-07-24 18:40:25.024139
129	maps	0hDQV9X1Da5JrwhK8gu86p	Fever To Tell (Deluxe Remastered)	https://i.scdn.co/image/ab67616d0000b2731b1cb4ef0f096f9d66fc3dc6	2003	f	219986	73	82	\N	Yeah Yeah Yeahs	SOLO	Let's delve into the creation of 'Maps'. This emotional track was written by Yeah Yeah Yeahs' Karen O, inspired by a breakup. The song was recorded in a heartfelt session at New York's Stratosphere Sound, capturing the band's raw emotion. 'Maps' not only became a chart-topping hit but also resonated deeply with listeners. The song's iconic chorus was a last-minute addition, adding to its emotional impact. So, next time you're feeling a bit lost, let this song guide you back!	2025-07-24 18:40:25.024139
130	float on	2lwwrWVKdf3LR9lbbhnr6R	Good News For People Who Love Bad News	https://i.scdn.co/image/ab67616d0000b273cc68329bfbf34037df965dc1	2004	f	208466	79	83	\N	Modest Mouse	SOLO	Now, let's dive into the story behind 'Float On' by Modest Mouse. Did you know that this track was a turning point for the band? It was written by Isaac Brock in a moment of personal struggle, aiming to create something uplifting. Recorded in a small studio in Portland, the song's infectious beat was inspired by a broken drum machine that gave it that unique groove. 'Float On' not only climbed the charts but also became an anthem for perseverance. And remember, folks, no matter how tough things get, just keep floating on! Keep it locked right here for more musical magic.	2025-07-24 18:40:25.024139
131	harder to breathe	4V9JDRqKjN8F2HWdlEDxvI	Songs About Jane: 10th Anniversary Edition	https://i.scdn.co/image/ab67616d0000b27392f2d790c6a97b195f66d51e	2002	f	173693	69	84	\N	Maroon 5	GROUP	Alright, let's talk about 'Harder to Breathe' by Maroon 5. This track was born out of frustration, penned by Adam Levine during a time when he felt creatively stifled. The song's raw energy was captured in a marathon recording session at Larrabee Studios in LA, where the band pushed their limits. Fun fact: the iconic guitar riff was an accidental discovery during a jam session. 'Harder to Breathe' not only marked Maroon 5's breakthrough but also resonated with anyone feeling the pressure of life. So, keep breathing, and stay tuned for more hits on this station!	2025-07-24 18:40:25.024139
132	ill be there for you	15tHagkk8z306XkyOHqiip	L.P.	https://i.scdn.co/image/ab67616d0000b273a2535194dfef3e77437036b5	1995	f	188359	71	85	\N	The Rembrandts	SOLO	You might be surprised to learn that 'I'll Be There for You' was originally intended to be a one-off for the Friends pilot. But its popularity soared so high that The Rembrandts were asked to include it on their album. The song's catchy hook was born out of a late-night jam session at Rumbo Recorders, where the band played around with different rhythms until they struck gold. And get this: the iconic opening line was inspired by a random phrase one of the songwriters overheard at a coffee shop. So, keep your dial right here, and we'll keep the hits coming, just for you!	2025-07-25 10:56:04.571883
133	where everybody knows your name	2uE8l7sar0JT0tZYhrPz8S	Keeper	https://i.scdn.co/image/ab67616d0000b2736bb85ed5053d24308e49d961	1983	f	151266	49	86	\N	Gary Portnoy	SOLO	Let me tell you a little secret about 'Where Everybody Knows Your Name': it was almost called 'People Like Us'! Gary Portnoy and Judy Hart Angelo crafted this heartwarming tune in a cozy New York studio, aiming to capture the essence of Cheers' welcoming atmosphere. The song's warm, inviting feel was achieved with a blend of acoustic guitars and soft percussion, creating that perfect 'home away from home' vibe. And here's a fun tidbit: the song's title phrase was inspired by a line from a poem Gary read. So, stay tuned, and we'll keep the good times rolling, right here on your favorite station!	2025-07-25 10:56:04.571883
134	the fresh prince of belair	0UREO3QWbXJW3gOUXpK1am	Greatest Hits	https://i.scdn.co/image/ab67616d0000b2735f9c08c7c4d2f37d5d73ce44	1988	f	177266	60	87	\N	DJ Jazzy Jeff & The Fresh Prince	SOLO	Get ready for a fun fact about 'The Fresh Prince of Bel-Air' theme song: it was recorded in just one take! DJ Jazzy Jeff and Will Smith, aka The Fresh Prince, brought their signature style to the track, blending hip-hop beats with a catchy narrative. The song was crafted at Sigma Sound Studios in Philadelphia, where the duo experimented with different sound effects to capture the essence of Will's journey. And did you know that the iconic 'yo, homes' line was improvised on the spot? So, keep your radio locked right here, and we'll keep the party going with more great tunes!	2025-07-25 10:56:04.571883
135	the golden girls	2i9ufVEMOr9jb0AbTGequu	Movie Soundtrack - Songs from Film & Tv	https://i.scdn.co/image/ab67616d0000b27396e893c7f9216dd50e28099e	1996	f	282706	3	88	\N	Andrew Gold	SOLO	Here's a little-known fact about 'The Golden Girls' theme song: Andrew Gold wrote it in just one afternoon! Inspired by the show's theme of friendship and laughter, Gold crafted this uplifting tune at his home studio in Los Angeles. The song's cheerful melody was achieved with a mix of acoustic and electric guitars, giving it that warm, inviting feel. And get this: the iconic 'thank you for being a friend' line was inspired by a greeting card Gold received. So, keep your dial right here, and we'll keep the good times rolling with more fantastic tunes!	2025-07-25 10:56:04.571883
136	the jeffersons	7u2g43fY31gjpPoLM7NJTG	Movin' On Up (From "The Jeffersons") [Piano Version]	https://i.scdn.co/image/ab67616d0000b27328f54565b0b80282d69b5234	1975	f	132486	4	89	\N	Ja'Net DuBois	SOLO	Did you know that 'The Jeffersons' theme song, 'Movin' On Up,' was written by Ja'Net DuBois herself? She penned this uplifting anthem in her living room, inspired by the show's theme of upward mobility. The song's catchy melody was recorded at a small studio in Los Angeles, where DuBois experimented with different vocal styles to capture the song's joyful spirit. And here's a fun fact: the iconic 'fish don't fry in the kitchen' line was inspired by a childhood memory of DuBois'. So, keep your radio tuned right here, and we'll keep the good times rolling with more fantastic tunes!	2025-07-25 10:56:04.571883
137	the brady bunch	1HyLRvrwqChIybFqycgu3M	It's A Sunshine Day : The Best Of The Brady Bunch	https://i.scdn.co/image/ab67616d0000b2734cc5ae1a7de063cb700b725d	1970	f	58933	39	91	\N	The Brady Bunch	SOLO	Here's a fun fact about 'The Brady Bunch' theme song: it was recorded by the actual cast members! The song's cheerful melody was crafted by Sherwood Schwartz and Frank De Vol at a studio in Hollywood, where the kids' voices were layered to create that iconic sound. And did you know that the song's title, 'The Brady Bunch,' was almost 'The Brady Brood'? So, keep your dial right here, and we'll keep the good times rolling with more fantastic tunes!	2025-07-25 10:56:04.571883
138	the munsters	5GAG0ZZmZeMQWMAvNGfoLT	The Munsters (Original Motion Picture Soundtrack)	https://i.scdn.co/image/ab67616d0000b27328eb6fe38bb8dfa087b66a1e	1964	f	33186	16	92	\N	Jack Marshall	SOLO	Let me share a little-known fact about 'The Munsters' theme song: it was composed by Jack Marshall in just one day! Inspired by the show's quirky characters, Marshall crafted this catchy tune at a studio in Los Angeles, blending surf rock elements with a spooky twist. The song's iconic opening riff was achieved with a unique guitar sound, giving it that eerie yet fun vibe. And here's a fun tidbit: the song's title was inspired by a line from a horror movie Marshall watched. So, keep your radio locked right here, and we'll keep the party going with more great tunes!	2025-07-25 10:56:04.571883
139	the beverly hillbillies	29qFlNOssruDfoEN8vN2Uu	Town and Country	https://i.scdn.co/image/ab67616d0000b273eb29e3e4514ef5f374778827	1962	f	140413	52	93	\N	Flatt & Scruggs	SOLO	Here's a little-known fact about 'The Beverly Hillbillies' theme song: it was written by Paul Henning, the show's creator, in just one evening! Flatt and Scruggs brought their bluegrass magic to the track, recording it at RCA Studio B in Nashville. The song's catchy banjo riff was inspired by a traditional folk tune, giving it that down-home feel. And did you know that the iconic 'come and listen to my story' line was inspired by a phrase Henning's grandfather used to say? So, keep your dial right here, and we'll keep the good times rolling with more fantastic tunes!	2025-07-25 10:56:04.571883
140	the andy griffith show	b6ad05c1f23a4373	Themes And Laughs From The Andy Griffith Show	https://i.scdn.co/image/ab67616d0000b273026813251389030d56973acd	1958	f	146666	9	94	\N	Earle Hagen	SOLO	Did you know that 'The Andy Griffith Show' theme song was composed by Earle Hagen in just one afternoon? Inspired by the show's small-town charm, Hagen crafted this iconic tune at a studio in Hollywood, blending a simple whistled melody with a warm, folksy feel. The song's catchy whistle was performed by Hagen himself, giving it that personal touch. And here's a fun fact: the song's title was inspired by a line from a poem Hagen read. So, keep your radio tuned right here, and we'll keep the good times rolling with more fantastic tunes!	2025-07-25 10:56:04.571883
141	the twilight zone	1i2ZoD6uWR4BjIhNuVhmW4	Pops Out Of This World	https://i.scdn.co/image/ab67616d0000b273e2945b30cec835cf9b8aa357	1960	f	218066	17	95	\N	Marius Constant	SOLO	Now, let's dive into the fascinating world of 'The Twilight Zone' theme. Composed by Marius Constant, this iconic piece was actually created from two separate pieces of music, 'Milieu No. 2' and 'Étrange No. 3', which were later combined to form the eerie and unforgettable theme we all know. Recorded at the CBS Television City in Hollywood, the use of unconventional instruments like the Ondioline adds a unique flavor to the sound. And here's a fun fact for you: the theme was so popular that it was even used in a 1960s dance craze called 'The Twilight Zone Dance'! Keep your dial right here, folks, as we keep exploring the magic of music.	2025-07-25 10:56:04.571883
142	hawaii fiveo	3UUwbJd2j4RORlalTUhaDk	Hawaii Five-O	https://i.scdn.co/image/ab67616d0000b2737c143568dc90032dea8d6183	1969	f	113893	53	97	\N	The Ventures	SOLO	Let's take a stroll through the surf rock paradise of 'Hawaii Five-O' by The Ventures. This track, penned by Morton Stevens, not only became a chart-topping hit but also inspired countless surf rock bands to pick up their guitars. Recorded at the legendary Western Recorders studio in Hollywood, the song's distinctive sound comes from the use of a Fender Jazzmaster guitar. Did you know that the song was so popular that it was even used as the theme for the 1980s video game 'Hawaii'? Stick around, music lovers, as we continue our journey through the waves of sound.	2025-07-25 10:56:04.571883
143	mission impossible	2QqouLGFYMynquwDMYUGk1	More Mission: Impossible	https://i.scdn.co/image/ab67616d0000b27339b4c54673ada0808ca87afe	1967	f	117733	43	98	\N	Lalo Schifrin	SOLO	Let's embark on a thrilling mission with 'Mission: Impossible' by Lalo Schifrin. This iconic theme was crafted in the heart of Hollywood at the Goldwyn Sound Stage, where Schifrin's innovative use of a piccolo trumpet gave the track its signature edge. The song's impact was so profound that it inspired a whole genre of spy music. And here's a bit of trivia for you: the theme was originally written in a 5/4 time signature, but was later changed to 6/8 for the TV series. Keep your ears tuned right here, folks, as we continue our musical adventure.	2025-07-25 10:56:04.571883
144	peter gunn	3RRdmSE4Vytb60hakTWNb3	Music From Peter Gunn	https://i.scdn.co/image/ab67616d0000b27345ea9c58a203d18bdaf906c6	1959	f	126333	43	99	\N	Henry Mancini	SOLO	Let's swing into the cool world of 'Peter Gunn' by Henry Mancini. This jazz-infused theme was recorded at the RCA Victor Studio in Hollywood, where Mancini's use of a muted trumpet and a walking bass line set the tone for the entire genre of detective show music. The song's success led to a Grammy win for Best Arrangement in 1959. And did you know that the theme was so popular that it inspired a short-lived dance called 'The Peter Gunn'? Keep your dial right here, music fans, as we keep grooving through the hits.	2025-07-25 10:56:04.571883
145	dragnet	7C13pyEILCVb39qvh0xtPA	Best Film-Noir Music of the 1950s, Vol.1 (Remastered 2024)	https://i.scdn.co/image/ab67616d0000b27372820f76739493cde89bf08b	1953	f	168124	1	100	\N	Walter Schumann	SOLO	Let's step into the noir world of 'Dragnet' by Walter Schumann. This iconic theme was recorded at the MGM Scoring Stage in Culver City, where Schumann's use of a four-note motif became synonymous with police procedurals. The song's impact was so significant that it was even parodied in numerous TV shows and movies. And here's a fun fact: the theme was originally written for a radio show before making its way to television. Stay tuned, folks, as we continue our journey through the sounds of the past.	2025-07-25 10:56:04.571883
146	the pink panther theme	0juPSJLFnLFim7BK6VzTes	The Pink Panther - Original Soundtrack	https://i.scdn.co/image/ab67616d0000b273e97407bb9fdb339614c3c7c1	1963	f	157680	56	99	\N	Henry Mancini	SOLO	Let's slip into the suave world of 'The Pink Panther Theme' by Henry Mancini. This playful piece was recorded at the RCA Victor Studio in Hollywood, where Mancini's use of a tenor saxophone and a whimsical melody set the tone for the entire franchise. The song's success led to a Grammy win for Best Instrumental Arrangement in 1964. And did you know that the theme was so popular that it inspired a dance called 'The Pink Panther'? Keep your ears tuned right here, music lovers, as we continue our musical escapade.	2025-07-25 10:56:04.571883
147	batman theme	3mICEHCCKuOrd6a3c8atst	The Music Of DC Comics: Vol. 2	https://i.scdn.co/image/ab67616d0000b2732c2213da3d68c7192bd21c28	1966	f	46893	31	103	\N	Neal Hefti	SOLO	Let's soar into the superhero world of the 'Batman Theme' by Neal Hefti. This iconic piece was recorded at the Goldwyn Sound Stage in Hollywood, where Hefti's use of a driving bass line and a catchy melody became synonymous with the Caped Crusader. The song's impact was so profound that it inspired countless covers and parodies. And here's a fun fact: the theme was originally written in a 12/8 time signature, but was later simplified for the TV series. Stay tuned, folks, as we continue our journey through the sounds of heroism.	2025-07-25 10:56:04.571883
148	star trek	1LaQ3RGV5wfIGEAsdUlkWA	The Ultimate Star Trek	https://i.scdn.co/image/ab67616d0000b273a7c00749fc2ff50e1cc184f4	1966	f	84093	32	104	\N	Alexander Courage	SOLO	Let's embark on a cosmic journey with the 'Star Trek' theme by Alexander Courage. This iconic piece was recorded at the Desilu Studios in Hollywood, where Courage's use of a theremin and a soaring melody set the tone for the entire franchise. The song's impact was so significant that it inspired countless sci-fi themes. And did you know that the theme was originally written for a different show before being adapted for 'Star Trek'? Keep your dial right here, music fans, as we continue our voyage through the stars.	2025-07-25 10:56:04.571883
149	the simpsons	1ipM6x72sFUJvNkmZxedl2	The City of Prague Philharmonic Orchestra Plays The Music Of Danny Elfman	https://i.scdn.co/image/ab67616d0000b273c8a3eecf982367241d99af30	1997	f	101813	19	106	\N	Danny Elfman	SOLO	Let's dive into the animated world of 'The Simpsons' theme by Danny Elfman. This catchy piece was recorded at the Todd-AO Scoring Stage in Hollywood, where Elfman's use of a quirky melody and a playful arrangement set the tone for the entire series. The song's impact was so profound that it inspired countless covers and parodies. And here's a fun fact: the theme was originally written for a different show before being adapted for 'The Simpsons'. Stay tuned, folks, as we continue our journey through the sounds of Springfield.	2025-07-25 10:56:04.571883
150	xfiles	2v4pLHpKG2c3HuY0Sv8xrq	X Files - I Want To Believe / OST	https://i.scdn.co/image/ab67616d0000b27337b70585050a1552fccfa60b	1996	f	351146	26	108	\N	Mark Snow	SOLO	Let's delve into the mysterious world of the 'X-Files' theme by Mark Snow. This eerie piece was recorded at the Paramount Scoring Stage in Hollywood, where Snow's use of a synthesizer and a haunting melody set the tone for the entire series. The song's impact was so significant that it inspired countless sci-fi themes. And did you know that the theme was originally written for a different show before being adapted for 'The X-Files'? Keep your ears tuned right here, music lovers, as we continue our journey through the unknown.	2025-07-25 10:56:04.571883
151	law and order	0IpOLDDlfk0I902oJMIBdK	Inventions From The Blue Line	https://i.scdn.co/image/ab67616d0000b27345f45174d7386556867f01b9	1990	f	195800	32	109	\N	Mike Post	SOLO	Mike Post's 'Law and Order' theme is a masterclass in tension and urgency, crafted to keep viewers glued to their seats. Did you know that Post wrote this iconic piece in just a few hours, inspired by the gritty realism of the show? The use of a driving bass line and sharp percussive elements was a deliberate choice to mirror the relentless pursuit of justice. And here's a fun fact: the theme was so effective that it was used in multiple international versions of the show, proving its universal appeal. Keep your dial right here for more fascinating stories behind the music!	2025-07-25 10:56:04.571883
152	csi crime scene investigation	0cJPLFrlV7TTCyPLupHzcH	Who's Next (Deluxe Edition)	https://i.scdn.co/image/ab67616d0000b273fe24dcd263c08c6dd84b6e8c	1978	f	511400	68	110	\N	The Who	GROUP	The Who's 'CSI: Crime Scene Investigation' theme, 'Who Are You,' was originally released in 1978 but found a new life in the early 2000s. Did you know that the song's inclusion in the series was a last-minute decision, chosen for its questioning lyrics that perfectly matched the show's investigative nature? The track was recorded at London's Ramport Studios, where the band's raw energy was captured in a way that still resonates with audiences today. And here's a bit of trivia: the song's iconic piano intro was played by none other than Roger Daltrey himself. Stay tuned for more behind-the-scenes magic!	2025-07-25 10:56:04.571883
153	the sopranos	0DHsVUhrKPAX3kpbyeb7B0	The Wimmin from W.O.M.B.L.E, Vol. 2	https://i.scdn.co/image/ab67616d0000b273d065270205feb58aeb88ed80	1997	f	197552	37	111	\N	Alabama 3	SOLO	Alabama 3's 'The Sopranos' theme, 'Woke Up This Morning,' is a soulful blend of blues and electronica that perfectly captures the show's dark and gritty atmosphere. Did you know that the song was originally inspired by a real-life incident involving a friend of the band's lead singer? The track was recorded in a small studio in London, where the band's unique sound was born from a mix of live instruments and electronic beats. And here's a fun fact: the song's opening line was sampled from a 1960s gospel record, adding an extra layer of depth to its haunting melody. Keep it locked right here for more intriguing tales from the world of music!	2025-07-25 10:56:04.571883
154	the west wing	09w6MNV0x0u4HmSnu2hJOy	The West Wing (Original Television Soundtrack)	https://i.scdn.co/image/ab67616d0000b2739ed595fe03a14d749ed56658	2000	f	232933	19	112	\N	W.G. Snuffy Walden	SOLO	W.G. Snuffy Walden's 'The West Wing' theme is a stirring piece that encapsulates the show's blend of drama and idealism. Did you know that Walden composed this piece in his home studio, drawing inspiration from the show's focus on political integrity? The theme's use of strings and piano creates a sense of urgency and hope, reflecting the show's narrative. And here's a bit of trivia: Walden was so dedicated to capturing the right mood that he reworked the theme multiple times until it perfectly matched the show's vision. Stay with us for more captivating stories behind the music!	2025-07-25 10:56:04.571883
155	er	0FCccVZfdb2JxqtO9UXrYm	Fantastic Beasts and Where to Find Them (Original Motion Picture Soundtrack)	https://i.scdn.co/image/ab67616d0000b273d12ff73aa7184b65484edf27	1997	f	208762	28	113	\N	James Newton Howard	SOLO	James Newton Howard's 'ER' theme is a heart-pounding piece that perfectly captures the show's high-stakes medical drama. Did you know that Howard composed this theme in his Los Angeles studio, using a combination of orchestral and electronic elements to create a sense of urgency? The theme's use of a driving rhythm and soaring strings was a deliberate choice to reflect the show's life-and-death scenarios. And here's a fun fact: Howard was so committed to the project that he spent weeks perfecting the theme to ensure it captured the show's emotional intensity. Keep your radio tuned right here for more behind-the-scenes insights!	2025-07-25 10:56:04.571883
156	the oc	497Fkp3gRiGrRMoqBTDudr	The Guest (Expanded Edition)	https://i.scdn.co/image/ab67616d0000b2733fffc3b7f3db4dcccff523e1	2002	f	193933	66	114	\N	Phantom Planet	SOLO	Phantom Planet's 'The O.C.' theme, 'California,' is an infectious anthem that perfectly captures the show's sunny, youthful vibe. Did you know that the song was written by the band's lead singer, Alex Greenwald, in just a few hours, inspired by the show's setting in Orange County? The track was recorded in a small studio in Los Angeles, where the band's energetic sound was captured in a way that still resonates with audiences today. And here's a bit of trivia: the song's catchy chorus was originally a placeholder, but it ended up becoming the song's defining feature. Stay tuned for more fascinating stories behind the music!	2025-07-25 10:56:04.571883
157	scrubs	3ffJKEoVfbiSlDHztViu6O	Scrubs	https://i.scdn.co/image/ab67616d0000b27386741ccef95520764f72e866	2002	f	218813	32	115	\N	Lazlo Bane	SOLO	Lazlo Bane's 'Scrubs' theme, 'Superman,' is a quirky and uplifting song that perfectly matches the show's blend of humor and heart. Did you know that the song was written by the band's lead singer, Chad Fischer, as a tribute to his father, who was a doctor? The track was recorded in a small studio in Los Angeles, where the band's unique sound was born from a mix of live instruments and electronic beats. And here's a fun fact: the song's opening line was inspired by a conversation Fischer had with his father about the challenges of being a doctor. Keep it locked right here for more intriguing tales from the world of music!	2025-07-25 10:56:04.571883
158	the office	0xpCrenke52qC3nY4f2ckT	The Office (Dashiin Remix)	https://i.scdn.co/image/ab67616d0000b2731f377fca5b39a58ee3728e9b	2005	f	254869	11	116	\N	The Scrantones	SOLO	The Scrantones' 'The Office' theme is a quirky and catchy piece that perfectly captures the show's blend of humor and awkwardness. Did you know that the theme was composed by the show's creator, Greg Daniels, who wanted a sound that reflected the show's unique setting in Scranton, Pennsylvania? The track was recorded in a small studio in Los Angeles, where the band's playful energy was captured in a way that still resonates with audiences today. And here's a bit of trivia: the theme's use of a xylophone was a deliberate choice to add a touch of whimsy to the show's opening. Stay with us for more captivating stories behind the music!	2025-07-25 10:56:04.571883
159	lost	0DNhUQCTDdAtuvxZXQ6krk	Lost: The Final Season (Original Television Soundtrack)	https://i.scdn.co/image/ab67616d0000b273864237f5bcb3f64e70199b00	2005	f	474506	40	118	\N	Michael Giacchino	SOLO	Michael Giacchino's 'Lost' theme is a haunting and mysterious piece that perfectly captures the show's sense of adventure and intrigue. Did you know that Giacchino composed this theme in his home studio, drawing inspiration from the show's focus on survival and mystery? The theme's use of a driving rhythm and eerie strings creates a sense of urgency and suspense, reflecting the show's narrative. And here's a fun fact: Giacchino was so dedicated to capturing the right mood that he reworked the theme multiple times until it perfectly matched the show's vision. Keep your radio tuned right here for more behind-the-scenes insights!	2025-07-25 10:56:04.571883
160	house	5o4lKT0ReFi73HuFexWEIY	Лучшие хиты: Trip Hop	https://i.scdn.co/image/ab67616d0000b273e622f6a4de8ac55ddf2ef889	1998	f	324933	45	119	\N	Massive Attack	SOLO	Massive Attack's 'House' theme, 'Teardrop,' is a haunting and atmospheric piece that perfectly captures the show's blend of medical drama and mystery. Did you know that the song was originally released in 1998 but found a new life in the early 2000s as the theme for 'House'? The track was recorded in a small studio in Bristol, where the band's unique sound was born from a mix of live instruments and electronic beats. And here's a bit of trivia: the song's use of a sampled heartbeat was a deliberate choice to reflect the show's focus on medical diagnostics. Stay tuned for more fascinating stories behind the music!	2025-07-25 10:56:04.571883
161	desperate housewives	2iuPMHqU7dvKK4ezEBTAgh	Desperate Housewives (TV Soundtrack)	https://i.scdn.co/image/ab67616d0000b27378804dd9c109691dbd318164	2004	f	40453	29	106	\N	Danny Elfman	SOLO	Now, let's dive into the magic behind 'Desperate Housewives'. Danny Elfman crafted this theme with a blend of suspense and whimsy, perfectly capturing the essence of the show. Recorded in his favorite studio, the piece features an eerie yet captivating violin solo that sets the tone for the series. Did you know that Elfman initially hesitated to take on the project, but once he did, he poured his heart into every note? And that's a wrap on this haunting melody, folks!	2025-07-25 10:56:04.571883
162	24	7drVZwMjU1tzXX0v1ldifT	24: The Game	https://i.scdn.co/image/ab67616d0000b273eea549d82dc8935fad7f092a	2002	f	288293	13	121	\N	Sean Callery	SOLO	Sean Callery's '24' theme is a masterclass in tension-building. The track was recorded in a marathon session, with Callery pushing the boundaries of traditional scoring. The use of a ticking clock in the background was a stroke of genius, symbolizing the real-time nature of the show. Fun fact: Callery once said that the theme was inspired by his own experiences with time management. And there you have it, a theme that keeps you on the edge of your seat!	2025-07-25 10:56:04.571883
163	the wire	4RjvJrkTa7gYOvk5tm94YW	...and all the pieces matter, Five Years of Music from The Wire (deluxe version)	https://i.scdn.co/image/ab67616d0000b273f0d0ac07e9d9a6f8f15fd53c	1982	f	104480	31	122	\N	Tom Waits	SOLO	Tom Waits brought his unique style to 'The Wire' theme, infusing it with a gritty, urban feel. The song was recorded in a makeshift studio in Baltimore, adding an authentic touch to the sound. Waits' raspy vocals and the haunting piano melody perfectly encapsulate the show's atmosphere. Did you know that Waits was a fan of the series before he agreed to contribute? And that's the story behind this unforgettable theme!	2025-07-25 10:56:04.571883
164	breaking bad	2hsLpiKNkWpd4e9QuVdhar	Breaking Bad: Original Score from the Television Series	https://i.scdn.co/image/ab67616d0000b2732aabcf79e0240e36f95877b5	2009	f	75666	51	123	\N	Dave Porter	SOLO	Dave Porter's 'Breaking Bad' theme is a journey through the dark and intense world of the series. The track was meticulously crafted to reflect the show's escalating tension, with Porter using unconventional instruments like the cello and the theremin. Recorded in a small studio in Albuquerque, the theme captures the essence of the show's setting. Trivia time: Porter once mentioned that the theme evolved as the series did, mirroring Walter White's transformation. And that's the tale of this gripping score!	2025-07-25 10:56:04.571883
165	mad men	1k5f1jOidJH55R0yLeZB0X	A Beautiful Mine (Mad Men Instrumental Theme) [From "Retrospective: The Music Of Mad M]	https://i.scdn.co/image/ab67616d0000b27393027a8b1dd5bd8ab58a4203	2002	f	205573	13	124	\N	RJD2	SOLO	RJD2's 'Mad Men' theme, 'A Beautiful Mine', is a blend of vintage and modern sounds that perfectly complements the show's aesthetic. The track was recorded in a studio filled with old-school equipment, giving it that authentic 60s vibe. RJD2's use of vinyl crackles and jazz elements adds a layer of sophistication. Fun fact: the theme was initially rejected but later embraced as the perfect fit. And that's the story behind this stylish tune!	2025-07-25 10:56:04.571883
166	true blood	4ytPgUsPNsKJtmM6Vjr4oS	TRUE BLOOD (Music from the HBO® Original Series)	https://i.scdn.co/image/ab67616d0000b2732a1072b4272e0b3115400d45	2006	f	163093	35	125	\N	Jace Everett	SOLO	Jace Everett's 'True Blood' theme, 'Bad Things', is a sultry and seductive piece that sets the mood for the series. The song was recorded in a Nashville studio, with Everett's deep, resonant voice adding to the allure. The use of a slide guitar gives it a haunting quality that fits the show's supernatural theme. Did you know that Everett was inspired by classic blues when writing this track? And that's the scoop on this mesmerizing theme!	2025-07-25 10:56:04.571883
167	dexter	32A1xdQk9lRSFn5CEY5M2S	Dexter Season 4	https://i.scdn.co/image/ab67616d0000b273d43946089226e9e1aac70a83	2007	f	102973	39	126	\N	Rolfe Kent	SOLO	Rolfe Kent's 'Dexter' theme is a chilling and intricate piece that mirrors the show's dark narrative. The track was recorded in a studio in Los Angeles, with Kent using a mix of orchestral and electronic elements to create a sense of unease. The theme's use of a solo cello adds a personal touch to the score. Trivia time: Kent once said that the theme was designed to reflect Dexter's dual nature. And that's the story behind this eerie melody!	2025-07-25 10:56:04.571883
168	weeds	3qnWCB2E4wbuz6OYLpClyD	Weeds (Music from the Original Series)	https://i.scdn.co/image/ab67616d0000b273e12bf606313af261012005dd	1967	f	100293	17	127	\N	Malvina Reynolds	SOLO	Malvina Reynolds' 'Weeds' theme, 'Little Boxes', is a quirky and catchy tune that perfectly captures the show's satirical tone. The song was recorded in a small studio in Berkeley, with Reynolds' distinctive voice and simple guitar accompaniment. The theme's use of repetitive lyrics adds to its charm. Fun fact: Reynolds wrote the song as a critique of suburban conformity, which aligns well with the series' themes. And that's the tale of this delightful track!	2025-07-25 10:56:04.571883
169	entourage	3LkejeQBFNMImUYEG0cXWV	The Royal Tenenbaums (Original Soundtrack)	https://i.scdn.co/image/ab67616d0000b273d6f0f7fa3ad98aa1d40a5c2b	2004	f	272133	25	128	\N	Mark Mothersbaugh	SOLO	Mark Mothersbaugh's 'Entourage' theme is a vibrant and energetic piece that reflects the show's fast-paced lifestyle. The track was recorded in a studio in Los Angeles, with Mothersbaugh using a mix of electronic and orchestral elements to create a dynamic sound. The theme's use of a driving beat adds to the excitement. Did you know that Mothersbaugh was inspired by the show's characters when composing this track? And that's the story behind this lively theme!	2025-07-25 10:56:04.571883
\.


--
-- Data for Name: track_list; Type: TABLE DATA; Schema: track_tables; Owner: postgres
--

COPY track_tables.track_list (id, name, curator, is_official, language, notes, created_at) FROM stdin;
1	Topspot Default List	Mr Ed Curator	t	English	This is the default list used for ranking in TopSpot, curated with horsepower and humor.	2025-07-26 20:56:03.723064
\.


--
-- Name: artist_id_seq; Type: SEQUENCE SET; Schema: core_tables; Owner: postgres
--

SELECT pg_catalog.setval('core_tables.artist_id_seq', 128, true);


--
-- Name: decade_id_seq; Type: SEQUENCE SET; Schema: core_tables; Owner: postgres
--

SELECT pg_catalog.setval('core_tables.decade_id_seq', 2, true);


--
-- Name: genre_id_seq; Type: SEQUENCE SET; Schema: core_tables; Owner: postgres
--

SELECT pg_catalog.setval('core_tables.genre_id_seq', 4, true);


--
-- Name: specialty_id_seq; Type: SEQUENCE SET; Schema: core_tables; Owner: postgres
--

SELECT pg_catalog.setval('core_tables.specialty_id_seq', 1, false);


--
-- Name: artistgenre_id_seq; Type: SEQUENCE SET; Schema: join_tables; Owner: postgres
--

SELECT pg_catalog.setval('join_tables.artistgenre_id_seq', 131, true);


--
-- Name: decadegenre_id_seq; Type: SEQUENCE SET; Schema: join_tables; Owner: postgres
--

SELECT pg_catalog.setval('join_tables.decadegenre_id_seq', 5, true);


--
-- Name: specialtyranking_id_seq; Type: SEQUENCE SET; Schema: ranking_tables; Owner: postgres
--

SELECT pg_catalog.setval('ranking_tables.specialtyranking_id_seq', 1, false);


--
-- Name: topartistgenreranking_id_seq; Type: SEQUENCE SET; Schema: ranking_tables; Owner: postgres
--

SELECT pg_catalog.setval('ranking_tables.topartistgenreranking_id_seq', 1, false);


--
-- Name: track_ranking_id_seq; Type: SEQUENCE SET; Schema: ranking_tables; Owner: postgres
--

SELECT pg_catalog.setval('ranking_tables.track_ranking_id_seq', 173, true);


--
-- Name: decade_genre_trivia_id_seq; Type: SEQUENCE SET; Schema: track_tables; Owner: postgres
--

SELECT pg_catalog.setval('track_tables.decade_genre_trivia_id_seq', 1, false);


--
-- Name: track_id_seq; Type: SEQUENCE SET; Schema: track_tables; Owner: postgres
--

SELECT pg_catalog.setval('track_tables.track_id_seq', 169, true);


--
-- Name: tracklist_id_seq; Type: SEQUENCE SET; Schema: track_tables; Owner: postgres
--

SELECT pg_catalog.setval('track_tables.tracklist_id_seq', 1, true);


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

