import{request,post}from'./client.js';
export const getRdReports=()=>request('/rd/reports');
export const getRdReport=id=>request('/rd/reports/'+id);
export const runRd=batchId=>post('/rd/reports',{batch_id:+batchId});
export const recomputeRd=id=>post('/rd/reports/'+id+'/recompute',{});
export const saveRdConclusion=(id,data)=>request(`/rd/reports/${id}/conclusion`,{method:'PATCH',body:JSON.stringify(data)});
