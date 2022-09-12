import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule } from '@angular/common/http';


import { AppComponent } from './app.component';
import { LogSelectorComponent } from './log-selector/log-selector.component';
import { LogViewerComponent } from './log-viewer/log-viewer.component';
import { LogNavbarComponent } from './log-navbar/log-navbar.component';

@NgModule({
  declarations: [
    AppComponent,
    LogSelectorComponent,
    LogViewerComponent,
    LogNavbarComponent
  ],
  imports: [
    BrowserModule,
    HttpClientModule
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule { }
