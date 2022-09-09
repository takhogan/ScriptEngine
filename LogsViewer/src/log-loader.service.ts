import { Injectable, OnInit } from '@angular/core';
import { BehaviorSubject, Subject, Subscription } from 'rxjs';
import { HttpClient, HttpEventType, HttpHeaders, HttpParams, HttpRequest, HttpResponse} from '@angular/common/http';

@Injectable({
  providedIn: 'root'
})
export class LogLoaderService implements OnInit {

  private logList : Array<LogObject>
  private selectedLogIndex : number;

  private selectedLogIndexSource = new BehaviorSubject<number>(null);
  private logListSource = new BehaviorSubject<Array<LogObject>>([]);

  selectedLogIndex$ = selectedLogIndexSource.asObservable();
  logList$ = logListSource.asObservable();

  constructor(private http : HttpClient) {
    this.logList = [];
    this.selectedLogIndex = null;
  }

  ngOnInit() {
    let params = new HttpParams();
      const req = new HttpRequest('POST', this.currentScript.props.deploymentTargetURL, formData);
      // let videoData : VideoData;
      this.subs.push(this.http.request(req).subscribe(event => {
        // this.videoDataLoadStatusSource.next('started');
        console.log('event body: ', event["body"]);
      },
      (err) => {
        if ((err !== undefined) && (err !== null)) {
          console.log('Upload Error! ', err);
        } else {
          console.log('Upload Error! undefined');
        }
        this.deployingScriptSource.next(false);
        // this.videoDataLoadStatusSource.next('failed');
      },
      () => {
        this.deployingScriptSource.next(false);
        // this.updateVideoSrc(videoSrc);
        // this.videoDataInit(videoData);
        // this.videoDataLoadStatusSource.next('finished');
        // window.setTimeout(() => {
        //   this.videoDataLoadStatusSource.next('none');
        // }, 4000);
      }));
  }


  updateSelectedLogIndex(logIndex) {
    if (logIndex === this.selectedLogIndex) {
      this.selectedLogIndex = null;
    } else {
      this.selectedLogIndex = logIndex;
    }
    this.selectedLogIndexSource.next(this.selectedLogIndex);
  }
}
