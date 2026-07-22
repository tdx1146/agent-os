/* app.js — 轻如烟组件框架
 * 每个组件有独立的容器和渲染函数，不碰别人的 DOM
 * 注册方式：CL.register('name', { container: 'id', render: fn, init: fn })
 */

var CL = (function() {
  var components = {};
  var registry = {};

  function register(name, spec) {
    if (registry[name]) throw '@' + name + ' already registered';
    spec.name = name;
    registry[name] = spec;
    // 注入容器
    var el = document.getElementById(spec.container);
    if (!el) {
      // 自动创建容器
      el = document.createElement('div');
      el.id = spec.container;
      var parent = document.getElementById(spec.parent) || document.body;
      parent.appendChild(el);
    }
    spec.el = el;
    if (spec.init) spec.init(spec);
    return spec;
  }

  function get(name) { return registry[name]; }

  function render(name) {
    var s = registry[name];
    if (!s) return;
    try { s.render(s, s.el); }
    catch(e) { console.error('CL.' + name + ' render error:', e); }
  }

  function renderAll() {
    for (var k in registry) render(k);
  }

  return { register: register, get: get, render: render, renderAll: renderAll };
})();
