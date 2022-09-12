import { Injectable, OnInit, OnDestroy } from '@angular/core';
import { BehaviorSubject, Subject, Subscription } from 'rxjs';
import { LogObject } from './types/log-viewer-types';
import { HttpClient, HttpEventType, HttpHeaders, HttpParams, HttpRequest, HttpResponse} from '@angular/common/http';
import { logViewerBackendURL } from './app-constants';

@Injectable({
  providedIn: 'root'
})
export class LogLoaderService implements OnInit,OnDestroy {

  private logList : Array<LogObject>
  private selectedLogIndex : number | null;

  private selectedLogIndexSource = new BehaviorSubject<number | null>(null);
  private logListSource = new BehaviorSubject<Array<LogObject>>([]);
  private subs : Array<Subscription>;

  selectedLogIndex$ = this.selectedLogIndexSource.asObservable();
  logList$ = this.logListSource.asObservable();

  constructor(private http : HttpClient) {
    this.logList = [];
    this.selectedLogIndex = null;
    this.subs = [];
    this.refreshLogList();
  }

  ngOnInit() {

  }

  ngOnDestroy() {
    this.subs.forEach(sub => {
      sub.unsubscribe();
    });
  }

  refreshLogList() {
    let formData = new FormData();
    // formData.append('file', zip, this.currentScript.scriptName + '.zip');
    let params = new HttpParams();
    const req = new HttpRequest('GET', logViewerBackendURL, formData);
    // let videoData : VideoData;

    this.subs.push(this.http.get<Array<LogObject>>(logViewerBackendURL).subscribe(logObjectArr => {
      console.log('loaded ', logObjectArr.length, ' elements');
      this.logList = logObjectArr;
      this.logListSource.next(this.logList);
    }, err => {
      console.log('error : ', err);
    }));
  }


  updateSelectedLogIndex(logIndex : number) {
    if (logIndex === this.selectedLogIndex) {
      this.selectedLogIndex = null;
    } else {
      this.selectedLogIndex = logIndex;
    }
    this.selectedLogIndexSource.next(this.selectedLogIndex);
  }
}
