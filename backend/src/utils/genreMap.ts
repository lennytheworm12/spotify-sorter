// Static genre normalization table
// Maps Spotify's granular genre strings into ~15 fixed buckets via keyword matching.
// Rules are priority-ordered — first match wins.

export const GENRE_BUCKETS = [
    'Hip Hop',
    'R&B',
    'Metal',
    'Jazz',
    'Classical',
    'Country',
    'Latin',
    'Reggae',
    'Folk',
    'Punk',
    'Electronic',
    'Indie',
    'Alternative',
    'Rock',
    'Pop',
    'Other',
] as const;

export type GenreBucket = (typeof GENRE_BUCKETS)[number];

// Each entry: [keywords to match against the lowercase genre string, bucket]
const GENRE_RULES: [string[], GenreBucket][] = [
    [['hip hop', 'rap', 'trap', 'drill', 'grime', 'phonk', 'plugg', 'cloud rap', 'boom bap', 'crunk', 'mumble'], 'Hip Hop'],
    [['r&b', 'soul', 'neo soul', 'funk', 'motown', 'quiet storm'], 'R&B'],
    [['metal', 'metalcore', 'deathcore'], 'Metal'],
    [['jazz', 'bebop', 'swing', 'blues', 'bossa nova'], 'Jazz'],
    [['classical', 'orchestral', 'opera', 'baroque', 'symphony', 'chamber'], 'Classical'],
    [['country', 'bluegrass', 'americana', 'outlaw', 'cowboy', 'western'], 'Country'],
    [['latin', 'reggaeton', 'salsa', 'cumbia', 'bachata', 'sertanejo', 'banda', 'corrido', 'norteno'], 'Latin'],
    [['reggae', 'ska', 'dub'], 'Reggae'],
    [['folk', 'singer-songwriter', 'acoustic'], 'Folk'],
    [['punk', 'hardcore', 'emo', 'post-hardcore'], 'Punk'],
    [['electronic', 'house', 'techno', 'edm', 'dubstep', 'drum and bass', 'dnb', 'trance', 'synth', 'electro', 'vaporwave', 'chillwave', 'lo-fi', 'lofi', 'vapor', 'glitch', 'breakbeat', 'rave', 'club'], 'Electronic'],
    [['indie', 'dream pop', 'shoegaze', 'bedroom pop', 'jangle', 'chillgaze'], 'Indie'],
    [['alternative', 'alt-'], 'Alternative'],
    [['rock', 'grunge', 'hard rock'], 'Rock'],
    [['pop', 'k-pop', 'j-pop', 'dance'], 'Pop'],
];

export function normalizeGenre(spotifyGenre: string): GenreBucket {
    const lower = spotifyGenre.toLowerCase();
    for (const [keywords, bucket] of GENRE_RULES) {
        if (keywords.some(kw => lower.includes(kw))) return bucket;
    }
    return 'Other';
}
