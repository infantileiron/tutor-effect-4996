/** @typedef {{id:number,code:string,name:string,campus:string,group:'control'|'intervention',score:number|null,absent:boolean}} Student */
/** @typedef {{id:number,title:string,campus:string,exclude_absent:boolean,description:string}} Plan */
/** @typedef {{id:number,plan_id:number,status:string,result:object|null,conclusion:string,published:boolean}} Report */
/** @typedef {{id:number,title:string,term:string,threshold:number,direction:'gte'|'lte',bandwidth:number|null,bandwidth_rule:'auto_min_side_n'|'manual',min_side_n:number,min_side_distinct:number,min_participation_jump:number,status:'draft'|'locking'|'locked',revision:number,roster_checksum:string,roster_count:number,candidate_count:number}} EligibilityBatch */
/** @typedef {{student_id:number,code:string,name:string,campus:string,enrollment_score:number,eligible:boolean,side:'left'|'right',participated:boolean,final_score:number|null}} RosterEntry */
/** @typedef {{id:number,batch_id:number,status:string,batch_revision:number,result:object|null,valid:boolean,published:boolean,invalidated_reason:string}} RdReport */
export const contractVersion=2;
