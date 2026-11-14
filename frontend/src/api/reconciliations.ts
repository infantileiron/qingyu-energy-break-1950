import {request} from "./client";
export const fetchReconciliations=()=>request("/reconciliations");
export const createReconciliation=(value:{run_a_id:string;run_b_id:string})=>request("/reconciliations","POST",value);
