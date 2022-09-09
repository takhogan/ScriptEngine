import { Injectable } from '@angular/core';
import { BehaviorSubject, Subject, Subscription } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class LogLoaderService {

  private logList : Array<LogObject>
  private selectedLogIndex : number;

  private selectedLogIndexSource = new BehaviorSubject<number>(null);
  private logListSource = new BehaviorSubject<Array<LogObject>>([]);

  selectedLogIndex$ = selectedLogIndexSource.asObservable();
  logList$ = logListSource.asObservable();

  constructor() {
    this.logList = [];
    this.selectedLogIndex = null;
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
