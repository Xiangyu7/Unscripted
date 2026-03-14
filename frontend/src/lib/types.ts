export interface Character {
  id: string;
  name: string;
  public_role: string;
  style: string;
  goal: string;
  suspicion: number;
  trust_to_player: number;
  location: string;
  knowledge?: string[];
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

export interface GameState {
  session_id: string;
  title: string;
  scene: string;
  phase: string;
  round: number;
  tension: number;
  characters: Character[];
  clues: Clue[];
  knowledge: Knowledge;
  events: GameEvent[];
  game_over: boolean;
  ending: string | null;
  max_rounds: number;
}

export interface NPCReply {
  character_id: string;
  character_name: string;
  text: string;
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
  system_narration: string;
  game_over: boolean;
  ending: string | null;
}

export interface FeedItem {
  id: string;
  type: "system" | "director" | "player" | "npc" | "clue" | "event" | "ending";
  text: string;
  character?: string;
}
