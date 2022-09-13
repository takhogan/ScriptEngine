import { SafeUrl } from '@angular/platform-browser';

export type LogObject = {
  log_path : String,
  log_timestamp : Date,
  log_imgs : Array<[SafeUrl, Date]>
}
