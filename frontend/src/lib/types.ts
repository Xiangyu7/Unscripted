export interface Character {
  id: string;
  name: string;
  public_role: string;
  style: string;
  goal: string;
  suspicion: number;
  trust_to_player: number;
  location: string;
  mood?: string;
  knowledge?: string[];
  portrait_url?: string;
}

export interface Clue {
  id: string;
  text: string;
  discovered: boolean;
}

export interface Knowledge {
  public_facts: string[];
  player_known: string[];
}

export interface GameEvent {
  round: number;
  type: string;
  text: string;
}

export interface VoteOption {
  id: string;
  label: string;
  kind: string;
}

export interface PublicStatement {
  character_id: string;
  character_name: string;
  text: string;
}

export interface VoteRecord {
  voter_id: string;
  voter_name: string;
  target_id: string;
  target_label: string;
  reason: string;
}

export interface VoteState {
  status: string;
  prompt: string;
  options: VoteOption[];
  public_statements: PublicStatement[];
  player_choice_id: string | null;
  votes: VoteRecord[];
  tally: Record<string, number>;
  winning_option_id: string | null;
  winning_option_label: string | null;
  outcome: string | null;
}

export interface CheckpointState {
  status: string; // "idle" | "awaiting_hypothesis" | "resolved"
  checkpoint_round: number;
  prompt: string;
  options: VoteOption[];
  player_choice_id: string | null;
  feedback: string | null;
}

export interface ConfrontationState {
  status: string; // "idle" | "awaiting_player_choice" | "resolved"
  target_character_id: string;
  target_character_name: string;
  evidence_clue_id: string;
  evidence_text: string;
  prompt: string;
  options: VoteOption[];
  player_choice_id: string | null;
  outcome: string | null;
  result_text: string | null;
}

export interface GameState {
  session_id: string;
  story_id?: string;
  title: string;
  scene: string;
  phase: string;
  round: number;
  tension: number;
  characters: Character[];
  clues: Clue[];
  knowledge: Knowledge;
  events: GameEvent[];
  vote_state?: VoteState | null;
  checkpoint_state?: CheckpointState | null;
  confrontation_state?: ConfrontationState | null;
  action_points: number;
  max_action_points: number;
  game_over: boolean;
  ending: string | null;
  max_rounds: number;
}

export interface ResetResponse {
  session_id: string;
  message: string;
  game_state: GameState | null;
}

export interface NPCReply {
  character_id: string;
  character_name: string;
  text: string;
  voice?: string | null;
  speed?: number | null;
}

export interface NPCEvent {
  text: string;
}

export interface TurnResponse {
  round: number;
  phase: string;
  tension: number;
  scene: string;
  director_note: string;
  new_clues: string[];
  npc_replies: NPCReply[];
  npc_events: NPCEvent[];
  public_statements: PublicStatement[];
  vote_records: VoteRecord[];
  system_narration: string;
  narrator_voice?: string | null;
  scene_image: string | null;
  game_over: boolean;
  ending: string | null;
  game_state: GameState | null;
}

export interface VoiceProviderState {
  provider: string;
  model: string | null;
  available: boolean;
  detail: string;
  fallback: string | null;
}

export interface VoiceStatusResponse {
  asr: VoiceProviderState;
  tts: VoiceProviderState;
}

export interface VoiceTranscriptionResponse {
  transcript: string;
  provider: string;
  model: string;
  latency_ms: number;
  usage?: Record<string, unknown> | null;
}

export interface VoiceTurnResponse {
  transcript: string;
  asr: VoiceTranscriptionResponse;
  turn: TurnResponse;
}

export interface SpeechSynthesisResponse {
  audio_base64: string;
  mime_type: string;
  provider: string;
  model: string;
  voice: string;
  latency_ms: number;
}

export interface FeedItem {
  id: string;
  type:
    | "system" | "director" | "player" | "npc" | "clue" | "event"
    | "ending" | "scene_image"
    | "truth_hint" | "dramatic_event"
    | "truth_replay" | "afterword" | "score_card"
    | "checkpoint" | "confrontation"
    | "action_blocked";
  text: string;
  character?: string;
  characterId?: string;
  imageUrl?: string;
  intensity?: string;
  mood?: string;
  // truth_replay fields
  step?: number;
  totalSteps?: number;
  // score_card fields
  totalScore?: number;
  rank?: string;
  rankTitle?: string;
  clueScore?: number;
  deductionScore?: number;
  efficiencyScore?: number;
  interactionScore?: number;
  // checkpoint / confrontation options
  options?: VoteOption[];
  prompt?: string;
  evidenceText?: string;
}

export interface ScoreCardData {
  total_score: number;
  rank: string;
  rank_title: string;
  clue_score: number;
  deduction_score: number;
  efficiency_score: number;
  interaction_score: number;
  summary: string;
}
