// static/js/scripts.js
// Additional JavaScript functionality for the dashboard

// Auto-refresh functionality
class AutoRefresh {
  constructor(interval = 30000) {
    this.interval = interval;
    this.timer = null;
    this.isPaused = false;
  }

  start() {
    if (this.timer) clearInterval(this.timer);
    this.timer = setInterval(() => {
      if (!this.isPaused && document.visibilityState === "visible") {
        this.refreshData();
      }
    }, this.interval);
  }

  pause() {
    this.isPaused = true;
  }

  resume() {
    this.isPaused = false;
  }

  refreshData() {
    // Trigger a refresh of all data
    if (typeof loadComputers === "function") {
      loadComputers();
    }

    // Show refresh indicator
    this.showRefreshIndicator();
  }

  showRefreshIndicator() {
    const indicator = document.createElement("div");
    indicator.className =
      "position-fixed top-0 end-0 m-3 p-2 bg-success text-white rounded";
    indicator.style.zIndex = "1050";
    indicator.innerHTML = `
            <i class="bi bi-arrow-clockwise me-2"></i>
            Data refreshed at ${new Date().toLocaleTimeString()}
        `;
    document.body.appendChild(indicator);

    // Remove indicator after 3 seconds
    setTimeout(() => {
      indicator.style.opacity = "0";
      indicator.style.transition = "opacity 0.5s";
      setTimeout(() => indicator.remove(), 500);
    }, 3000);
  }
}

// Notification system
class NotificationSystem {
  constructor() {
    this.container = null;
    this.init();
  }

  init() {
    this.container = document.createElement("div");
    this.container.id = "notification-container";
    this.container.className = "position-fixed top-0 end-0 m-3";
    this.container.style.zIndex = "1060";
    document.body.appendChild(this.container);
  }

  show(message, type = "info", duration = 5000) {
    const notification = document.createElement("div");
    notification.className = `alert alert-${type} alert-dismissible fade show`;
    notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

    this.container.appendChild(notification);

    // Auto remove after duration
    setTimeout(() => {
      if (notification.parentNode) {
        notification.classList.remove("show");
        setTimeout(() => notification.remove(), 500);
      }
    }, duration);
  }
}

// Computer status visualization
class StatusVisualizer {
  static updateStatusBadge(element, status) {
    const badges = {
      online: "bg-success",
      offline: "bg-danger",
      warning: "bg-warning",
      unknown: "bg-secondary",
    };

    const badgeClass = badges[status] || "bg-secondary";

    // Remove existing badge classes
    element.className = element.className.replace(/bg-\w+/g, "");
    element.classList.add("badge", badgeClass);
    element.textContent = status.charAt(0).toUpperCase() + status.slice(1);

    // Add animation for status changes
    element.classList.add("status-change");
    setTimeout(() => {
      element.classList.remove("status-change");
    }, 500);
  }
}

// Dashboard statistics updater
class DashboardStats {
  static updateStats(online, offline, total) {
    // Update stats cards
    const updateStatCard = (selector, value, type = "count") => {
      const element = document.querySelector(selector);
      if (!element) return;

      if (type === "percentage") {
        const percentage =
          total > 0 ? ((online / total) * 100).toFixed(1) : "0";
        element.textContent = `${percentage}%`;
      } else {
        element.textContent = value;
      }
    };

    updateStatCard(".card.bg-primary h2", total);
    updateStatCard(".card.bg-success h2", online);
    updateStatCard(".card.bg-danger h2", offline);
    updateStatCard(".card.bg-warning h2", null, "percentage");
  }
}

// Initialize when document is ready
document.addEventListener("DOMContentLoaded", function () {
  // Initialize auto-refresh
  const autoRefresh = new AutoRefresh(30000); // 30 seconds
  autoRefresh.start();

  // Initialize notification system
  const notifications = new NotificationSystem();

  // Pause auto-refresh when tab is not visible
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      autoRefresh.pause();
    } else {
      autoRefresh.resume();
    }
  });

  // Keyboard shortcuts
  document.addEventListener("keydown", function (e) {
    // Ctrl+R or Cmd+R to manually refresh
    if ((e.ctrlKey || e.metaKey) && e.key === "r") {
      e.preventDefault();
      autoRefresh.refreshData();
      notifications.show("Manual refresh triggered", "info");
    }

    // F1 to show help
    if (e.key === "F1") {
      e.preventDefault();
      alert(
        "Keyboard Shortcuts:\n\n" +
          "Ctrl+R / Cmd+R - Refresh data\n" +
          "F1 - Show this help\n" +
          "Esc - Close modal/dialog"
      );
    }
  });

  // Enhanced modal handling
  const modals = document.querySelectorAll(".modal");
  modals.forEach((modal) => {
    modal.addEventListener("shown.bs.modal", function () {
      // Focus first input in modal
      const input = this.querySelector(
        'input[type="text"], input[type="email"], input[type="password"]'
      );
      if (input) input.focus();
    });
  });

  // Tooltip initialization
  const tooltipTriggerList = [].slice.call(
    document.querySelectorAll('[data-bs-toggle="tooltip"]')
  );
  tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new bootstrap.Tooltip(tooltipTriggerEl);
  });
});
