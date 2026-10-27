#!/usr/bin/env node
import {readFile} from "node:fs/promises";
import {resolve} from "node:path";

const root=resolve(import.meta.dirname,"..");
const [html,css,js]=await Promise.all([
  readFile(resolve(root,"frontend/dashboard/index.html"),"utf8"),
  readFile(resolve(root,"frontend/dashboard/styles.css"),"utf8"),
  readFile(resolve(root,"frontend/dashboard/app.js"),"utf8"),
]);
const modules=["quality","runs","regression","issues","feedback","handoffs","rag","system"];
for(const view of modules){
  if(!html.includes(`data-view="${view}"`)||!html.includes(`data-dashboard-view="${view}"`))throw new Error(`missing dashboard module ${view}`);
}
if((html.match(/data-view=/g)||[]).length!==modules.length)throw new Error(`dashboard must expose exactly ${modules.length} primary modules`);
for(const removed of ["工具运行器","运行任务 0 换货演示","config-policy","environment-summary"]){
  if(html.includes(removed)||js.includes(removed))throw new Error(`legacy surface remains: ${removed}`);
}
for(const route of ["/api/v1/quality/overview","/api/v1/regression/batches","/api/v1/system/status"]){
  if(!js.includes(route))throw new Error(`missing API integration ${route}`);
}
if(!css.includes("@media(max-width:760px)"))throw new Error("mobile breakpoint missing");
if(!css.includes("minmax(0,1fr)"))throw new Error("overflow-safe grid missing");
console.log(`Dashboard UI contract validation passed: ${modules.length} modules, responsive layout, formal APIs.`);
