export type State = 'IDLE' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'ERROR';
export type ReceiverState = 'AWAITING_ACK' | 'SYNCED' | 'LAGGING' | 'STALE' | 'DISCONNECTED';
export interface Candidate { candidate_id: string; candidate_name: string; ballot_number: number; party_name: string }
export interface Catalog { candidates: Candidate[]; regions: { region_id: string; region_name: string; region_level: string }[] }
export interface Region { region_id: string; target_ballots: number; target_ballots_basis: string; counted_votes: number; valid_votes: number; invalid_votes: number; count_rate_pct: number; candidate_votes: { candidate_id: string; votes: number; vote_share_pct: number | null }[] }
export interface Receiver { transport: 'CONNECTED' | 'DISCONNECTED'; receiver_state: ReceiverState; run_id: string; last_sent_seq: number; last_acked_seq: number | null; last_ack_at: string | null; last_heartbeat_at: string | null; ack_lag_events: number | null; evidence_mode: 'FIXTURE' | 'LIVE'; live_verified: boolean; ack_timeout_ms: number; heartbeat_timeout_ms: number }
export interface Frame { contract_version: string; contract_status: string; election_id: string; election_type: string; data_mode: string; simulated: boolean; notice: string; reference: { verification_status: string; results_as_of: null; results_as_of_precision: string; [key: string]: unknown }; type: 'snapshot' | 'update' | 'status' | 'error'; run_id: string; seq: number; event_time: string; emitted_at: string; state: State; snapshot_id?: string; sync_cursor_seq?: number; scope_region_ids?: string[]; regions?: Region[]; catalog?: Catalog; system2?: Receiver; reason?: string; error?: { code: string; message: string; retryable?: boolean }; last_good_snapshot_id?: string }
export interface Log { id: number; frame: Frame; outcome: 'APPLIED' | 'REJECTED' | 'IGNORED'; message?: string; observed_at: string }
export interface View { state: State; run: string; cursor: number; snapshot: Frame; history: Frame[]; receiver: Receiver; transport: 'CONNECTED' | 'DISCONNECTED'; stale: boolean; logs: Log[]; error: string | null; lastEvent: Frame; busy: boolean; note: string }
export type Scenario = 'normal' | 'invalid' | 'receiver-disconnect' | 'ws-disconnect' | 'ack-wait' | 'lagging' | 'stale';
export type Command = 'start' | 'stop' | 'reset';
export interface Adapter { getSnapshot(): View; subscribe(listener: () => void): () => void; command(command: Command): Promise<void>; dispose(): void }

