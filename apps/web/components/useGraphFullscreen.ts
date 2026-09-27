'use client';
import {useCallback,useEffect,useRef,useState,type RefObject} from 'react';

/** Native fullscreen where supported; an expanded workspace inside restricted WebViews. */
export function useGraphFullscreen(stage:RefObject<HTMLElement|null>){
 const [expanded,setExpanded]=useState(false);
 const returnFocus=useRef<HTMLElement|null>(null);
 const exit=useCallback(async()=>{
  if(document.fullscreenElement===stage.current)await document.exitFullscreen().catch(()=>{});
  setExpanded(false);
  returnFocus.current?.focus();
 },[stage]);
 const toggle=useCallback(async()=>{
  if(expanded){await exit();return;}
  const target=stage.current;if(!target)return;
  returnFocus.current=document.activeElement instanceof HTMLElement?document.activeElement:null;
  setExpanded(true);
  try{if(document.fullscreenEnabled&&target.requestFullscreen)await target.requestFullscreen();}catch{/* Expanded CSS view remains available. */}
  target.querySelector<HTMLButtonElement>('[data-fullscreen-toggle]')?.focus();
 },[expanded,exit,stage]);
 useEffect(()=>{
  const change=()=>{if(!document.fullscreenElement){setExpanded(false);returnFocus.current?.focus();}};
  document.addEventListener('fullscreenchange',change);
  return()=>document.removeEventListener('fullscreenchange',change);
 },[]);
 useEffect(()=>{
  if(!expanded)return;
  const previous=document.body.style.overflow;document.body.style.overflow='hidden';
  const key=(event:KeyboardEvent)=>{
   if(event.key==='Escape'){event.preventDefault();void exit();return;}
   if(event.key!=='Tab')return;
   const items=[...stage.current?.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),a[href],[tabindex="0"]')||[]].filter(e=>e.getClientRects().length>0);
   const first=items[0],last=items.at(-1);if(!first||!last)return;
   if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
   else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  };
  document.addEventListener('keydown',key);
  return()=>{document.body.style.overflow=previous;document.removeEventListener('keydown',key);};
 },[expanded,exit,stage]);
 return {expanded,toggle};
}
