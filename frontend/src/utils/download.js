export async function downloadReport(id,token,kind='tutor-effect-report'){
 const path=kind==='rd-report'?`/api/rd/reports/${id}/export`:`/api/reports/${id}/export`;
 const response=await fetch(path,{headers:{Authorization:`Bearer ${token}`}});
 if(!response.ok){let detail='导出失败，请确认报告已完成';try{detail=(await response.json()).detail||detail;}catch(e){}throw new Error(detail);}
 const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=`${kind}-${id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
