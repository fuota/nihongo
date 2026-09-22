export type FuriganaSegment = {
  surface: string;
  reading: string | null;
};

export type CharacterRef = {
  id: string;
  character: string;
};

export type VocabWord = {
  id: string;
  kanji: string | null;
  reading: string;
  meaning: string;
  example_sentence: string | null;
  example_sentence_en: string | null;
  example_sentence_furigana: FuriganaSegment[] | null;
  jlpt_level: string;
  topic: string | null;
  is_learnt: boolean;
  in_drill: boolean;
  characters?: CharacterRef[];
};

export type KanjiCompound = {
  id: string;
  kanji: string | null;
  reading: string;
  meaning: string;
};

export type KanjiDetail = {
  id: string;
  character: string;
  character_type: string;
  romaji: string | null;
  meaning: string | null;
  onyomi: string[] | null;
  kunyomi: string[] | null;
  stroke_count: number;
  stroke_paths: string[];
  jlpt_level: string;
  topic: string | null;
  compounds: KanjiCompound[];
};

export type GrammarPattern = {
  id: string;
  pattern: string;
  explanation: string;
  example_sentence: string | null;
  example_sentence_en: string | null;
  example_sentence_furigana: FuriganaSegment[] | null;
  drill_sentence: string | null;
  jlpt_level: string;
  is_learnt: boolean;
  in_drill: boolean;
};

export type SessionVocabItem = VocabWord & { content_type: 'vocab' };
export type SessionGrammarItem = GrammarPattern & { content_type: 'grammar' };
export type SessionItem = SessionVocabItem | SessionGrammarItem;

export type DrillVocabQuestion = {
  content_type: 'vocab';
  content_id: string;
  question_kind: 'reading' | 'meaning';
  prompt: string;
  options: string[];
  correct_answer: string;
};

export type DrillGrammarQuestion = {
  content_type: 'grammar';
  content_id: string;
  drill_sentence: string;
  options: string[];
  correct_answer: string;
};

export type DrillWritingQuestion = {
  content_type: 'writing';
  content_id: string;
  character: string;
  meaning: string | null;
  romaji: string | null;
  stroke_paths: string[];
};

export type DrillQuestion = DrillVocabQuestion | DrillGrammarQuestion | DrillWritingQuestion;

export type ComprehensionQuestion = {
  question: string;
  options: string[];
  correct_answer: string;
};

export type ReadingSession = {
  session_id: string;
  status: 'in_progress' | 'completed';
  reasoning: string;
  passage: string;
  passage_furigana: FuriganaSegment[] | null;
  questions: ComprehensionQuestion[];
  answers: (string | null)[] | null;
  score: number | null;
  review: string | null;
  created_at: string;
};

export type ReadingHistoryEntry = {
  session_id: string;
  status: 'in_progress' | 'completed';
  passage_preview: string;
  score: number | null;
  total: number;
  created_at: string;
};

export const JLPT_LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1'] as const;
