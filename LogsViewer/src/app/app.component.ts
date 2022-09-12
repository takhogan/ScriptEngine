import { Component, OnInit, OnDestroy } from '@angular/core';
import { LogObject } from '../types/log-viewer-types';
import { Subscription } from 'rxjs';
import { LogLoaderService } from '../log-loader.service';


@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnDestroy, OnInit {
  selectedLogIndex : number | null;
  logList : Array<LogObject>;

  private subs : Array<Subscription>;

  constructor(private logLoader : LogLoaderService) {
    this.selectedLogIndex = null;
    this.logList = [];
    this.subs = [];
  }

  ngOnInit() {
    this.subs.push(this.logLoader.selectedLogIndex$.subscribe(logIndex => {
      this.selectedLogIndex = logIndex
    }));
    this.subs.push(this.logLoader.logList$.subscribe(logList => {
      this.logList = logList;
    }))
  }

  ngOnDestroy() {
    this.subs.forEach(sub => {
      sub.unsubscribe();
    });
  }
}
