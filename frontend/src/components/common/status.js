import{STATUS,BATCH_STATUS,RD_STATUS}from'../../constants/enums.js';
export const badge=status=>`<span class="badge ${status}">${STATUS[status]||status}</span>`;
export const batchBadge=status=>`<span class="badge ${status}">${BATCH_STATUS[status]||status}</span>`;
export const rdBadge=status=>`<span class="badge ${status}">${RD_STATUS[status]||status}</span>`;
