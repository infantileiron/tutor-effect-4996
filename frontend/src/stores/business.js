import{getStudents}from'../api/students.js';import{getPlans}from'../api/plans.js';import{getReports}from'../api/reports.js';import{getBatches,getBatch}from'../api/eligibility.js';import{getRdReports}from'../api/rd.js';
export const store={students:[],plans:[],reports:[],batches:[],batchDetail:null,rdReports:[],user:null};
export async function refresh(){
 [store.students,store.plans,store.reports,store.batches,store.rdReports]=await Promise.all([getStudents(),getPlans(),getReports(),getBatches(),getRdReports()]);
}
export async function loadBatch(id){store.batchDetail=await getBatch(id);return store.batchDetail;}
