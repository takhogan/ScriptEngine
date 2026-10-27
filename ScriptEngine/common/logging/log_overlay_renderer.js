// Renders a ScreenPlan log overlay (see log_overlay.py for the format).
//
// This file is inlined into every *.overlay.html log file, so opening one in a
// browser shows the annotated image. It draws to a 2D canvas and only
// approximates OpenCV's rasterisation (blur, line ends, circle edges); the
// Python renderer in log_overlay.py is the exact one.
(function () {
  'use strict';

  function makeCanvas(width, height) {
    var canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    return canvas;
  }

  function loadImage(src) {
    return new Promise(function (resolve, reject) {
      var image = new Image();
      image.onload = function () { resolve(image); };
      image.onerror = function () { reject(new Error('could not load ' + src)); };
      image.src = src;
    });
  }

  // Loads every entry of document.images. `srcFor` returns the URL to load an
  // entry from (default: its href, relative to the overlay file).
  function loadImages(images, srcFor) {
    var loaded = {};
    return Promise.all(Object.keys(images).map(function (key) {
      return Promise.resolve(srcFor(key, images[key])).then(loadImage).then(function (image) {
        loaded[key] = image;
      });
    })).then(function () { return loaded; });
  }

  function blurSigma(kernel) {
    // OpenCV's sigma for a kernel size when sigma is 0.
    return 0.3 * ((kernel - 1) * 0.5 - 1) + 0.8;
  }

  function blurCanvas(ctx, kernel) {
    var canvas = ctx.canvas;
    var w = canvas.width, h = canvas.height;
    var sigma = blurSigma(kernel);
    var pad = Math.ceil(sigma * 3);
    // Extend the edges first so the blur replicates the border like
    // BORDER_REPLICATE instead of fading to transparent.
    var padded = makeCanvas(w + 2 * pad, h + 2 * pad);
    var pctx = padded.getContext('2d');
    pctx.imageSmoothingEnabled = false;
    pctx.drawImage(canvas, pad, pad);
    pctx.drawImage(canvas, 0, 0, w, 1, pad, 0, w, pad);
    pctx.drawImage(canvas, 0, h - 1, w, 1, pad, h + pad, w, pad);
    pctx.drawImage(padded, pad, 0, 1, h + 2 * pad, 0, 0, pad, h + 2 * pad);
    pctx.drawImage(padded, w + pad - 1, 0, 1, h + 2 * pad, w + pad, 0, pad, h + 2 * pad);
    ctx.save();
    ctx.filter = 'blur(' + sigma + 'px)';
    ctx.drawImage(padded, -pad, -pad);
    ctx.restore();
  }

  function fillBox(ctx, x1, y1, x2, y2) {
    var left = Math.min(x1, x2), top = Math.min(y1, y2);
    ctx.fillRect(left, top, Math.abs(x2 - x1) + 1, Math.abs(y2 - y1) + 1);
  }

  function drawRect(ctx, layer) {
    var x1 = layer.p1[0], y1 = layer.p1[1], x2 = layer.p2[0], y2 = layer.p2[1];
    ctx.fillStyle = layer.color;
    if (layer.thickness < 0) {
      fillBox(ctx, x1, y1, x2, y2);
      return;
    }
    // Each edge is a band `thickness` pixels wide centred on the corner line,
    // so a 1px rectangle lands exactly on OpenCV's pixels.
    var left = Math.min(x1, x2), right = Math.max(x1, x2);
    var top = Math.min(y1, y2), bottom = Math.max(y1, y2);
    var half = Math.floor(layer.thickness / 2);
    var extra = layer.thickness - 1 - half;
    fillBox(ctx, left - half, top - half, right + extra, top + extra);
    fillBox(ctx, left - half, bottom - half, right + extra, bottom + extra);
    fillBox(ctx, left - half, top - half, left + extra, bottom + extra);
    fillBox(ctx, right - half, top - half, right + extra, bottom + extra);
  }

  function drawLayers(ctx, layers, images) {
    layers.forEach(function (layer) {
      var source, temp, tctx;
      switch (layer.op) {
        case 'image':
          source = images[layer.image];
          var src = layer.src || [0, 0, source.naturalWidth, source.naturalHeight];
          ctx.drawImage(source, src[0], src[1], src[2], src[3],
                        layer.at[0], layer.at[1], src[2], src[3]);
          break;
        case 'blur':
          blurCanvas(ctx, layer.kernel);
          break;
        case 'group':
          temp = makeCanvas(ctx.canvas.width, ctx.canvas.height);
          tctx = temp.getContext('2d');
          tctx.imageSmoothingEnabled = false;
          tctx.drawImage(ctx.canvas, 0, 0);
          drawLayers(tctx, layer.layers, images);
          ctx.save();
          ctx.globalAlpha = layer.opacity;
          ctx.drawImage(temp, 0, 0);
          ctx.restore();
          break;
        case 'frame':
          temp = makeCanvas(layer.width, layer.height);
          tctx = temp.getContext('2d');
          tctx.imageSmoothingEnabled = false;
          tctx.fillStyle = '#000';
          tctx.fillRect(0, 0, layer.width, layer.height);
          drawLayers(tctx, layer.layers, images);
          ctx.drawImage(temp, layer.at[0], layer.at[1]);
          break;
        case 'rect':
          drawRect(ctx, layer);
          break;
        case 'circle':
          ctx.beginPath();
          ctx.arc(layer.center[0] + 0.5, layer.center[1] + 0.5, layer.radius + (layer.thickness < 0 ? 0.5 : 0), 0, 2 * Math.PI);
          if (layer.thickness < 0) {
            ctx.fillStyle = layer.color;
            ctx.fill();
          } else {
            ctx.strokeStyle = layer.color;
            ctx.lineWidth = layer.thickness;
            ctx.stroke();
          }
          break;
        case 'polyline':
          ctx.save();
          ctx.strokeStyle = layer.color;
          ctx.lineWidth = layer.thickness;
          ctx.lineCap = 'round';
          ctx.lineJoin = 'round';
          ctx.beginPath();
          layer.points.forEach(function (point, index) {
            if (index === 0) ctx.moveTo(point[0] + 0.5, point[1] + 0.5);
            else ctx.lineTo(point[0] + 0.5, point[1] + 0.5);
          });
          ctx.stroke();
          ctx.restore();
          break;
        case 'mask':
          // Masks are stored with the mask in the alpha channel. Stamp it at
          // the five offsets of a radius-1 circle, then colour what it covers.
          // Only compositing is used, never pixel reads, so this works on
          // file:// pages where the canvas is tainted.
          source = images[layer.image];
          temp = makeCanvas(ctx.canvas.width, ctx.canvas.height);
          tctx = temp.getContext('2d');
          [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]].forEach(function (offset) {
            tctx.drawImage(source, layer.at[0] + offset[0], layer.at[1] + offset[1]);
          });
          tctx.globalCompositeOperation = 'source-in';
          tctx.fillStyle = layer.color;
          tctx.fillRect(0, 0, temp.width, temp.height);
          ctx.drawImage(temp, 0, 0);
          break;
        default:
          throw new Error('unknown overlay op: ' + layer.op);
      }
    });
  }

  // Draws `doc` onto `canvas`. Returns a promise that settles when it is drawn.
  function render(doc, canvas, srcFor) {
    srcFor = srcFor || function (key, entry) { return entry.href; };
    return loadImages(doc.images, srcFor).then(function (images) {
      canvas.width = doc.width;
      canvas.height = doc.height;
      var ctx = canvas.getContext('2d');
      ctx.imageSmoothingEnabled = false;
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, doc.width, doc.height);
      drawLayers(ctx, doc.layers, images);
      return canvas;
    });
  }

  var api = { render: render, version: 1 };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.ScreenPlanOverlay = api;

  // Self-render when this script is inside an overlay HTML file.
  if (typeof document !== 'undefined') {
    var dataBlock = document.getElementById('screenplan-overlay');
    var target = document.getElementById('screenplan-overlay-canvas');
    if (dataBlock && target) {
      var doc = JSON.parse(dataBlock.textContent);
      render(doc, target).then(function () {
        document.body.setAttribute('data-rendered', 'true');
      }, function (error) {
        var message = document.getElementById('screenplan-overlay-error');
        if (message) {
          message.textContent = 'Could not render this log overlay: ' + error.message +
            '. The screenshot it draws on must be in the same run folder.';
        }
        document.body.setAttribute('data-rendered', 'error');
      });
    }
  }
})();
