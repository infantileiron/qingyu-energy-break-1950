export type Role="admin"|"analyst"|"viewer";
export interface User{email:string;role:Role}
export interface Entity{id:string;created_at:string;[key:string]:any}
export interface Observation{timestamp:string;kwh:number;output_kg:number;intensity:number;score:number;baseline:number;anomaly:boolean}
export interface Segment{start_index:number;end_index:number;count:number;mean:number;sse:number;start_at:string;end_at:string}
export interface ReconciliationHour{
 timestamp:string;kwh_a:number;kwh_b:number;kwh_delta:number;
 output_a_kg:number;output_b_kg:number;intensity_a:number;intensity_b:number;
 output_effect:number;intensity_effect:number;residual:number
}
export interface ReconciliationSideRow{timestamp:string;side:"a"|"b";state:"valid"|"excluded";reason:string;kwh:number|null;output_kg:number|null}
export interface ReconciliationLedger{
 schema_version:number;common_count:number;hourly:ReconciliationHour[];
 only_a:ReconciliationSideRow[];only_b:ReconciliationSideRow[];
 only_a_count:number;only_b_count:number;
 totals:{kwh_a:number;kwh_b:number;kwh_delta:number;output_a_kg:number;output_b_kg:number;output_effect:number;intensity_effect:number;attributed_delta:number;unattributed_kwh:number};
 has_common_hours:boolean
}
export interface Reconciliation{id:string;created_at:string;run_a_id:string;run_b_id:string;snapshot:{run_a_id:string;run_b_id:string;run_a_label:string;run_b_label:string;frozen_run_a:{id:string;created_at:string;valid_count:number;excluded_count:number};frozen_run_b:{id:string;created_at:string;valid_count:number;excluded_count:number};ledger:ReconciliationLedger}}
