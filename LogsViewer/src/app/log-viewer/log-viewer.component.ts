import { Component, Input, OnInit } from '@angular/core';
import { LogObject } from '../../types/log-viewer-types';

@Component({
  selector: 'app-log-viewer',
  templateUrl: './log-viewer.component.html',
  styleUrls: ['./log-viewer.component.css']
})
export class LogViewerComponent implements OnInit {

  @Input() logObj : LogObject;

  constructor() {
    this.logObj = {
      log_path : '',
      log_timestamp : new Date(),
      log_imgs : []
    };
  }

  ngOnInit(): void {

  }

}
