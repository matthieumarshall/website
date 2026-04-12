"use strict";

// Initialize fixture image modal functionality when images are rendered
function initializeFixtureImageModal() {
  const modal = document.getElementById('fixture-image-modal');
  if (!modal) return;

  const modalContent = document.getElementById('fixture-image-modal-content');
  const closeButton = document.querySelector('.fixture-image-modal-close');
  const fixtureImages = document.querySelectorAll('.fixture-image');

  // Open modal when image is clicked
  fixtureImages.forEach(img => {
    img.addEventListener('click', () => {
      modalContent.src = img.src;
      modalContent.alt = img.alt;
      modal.showModal();
    });

    // Allow opening modal with Enter/Space keys for accessibility
    img.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        modalContent.src = img.src;
        modalContent.alt = img.alt;
        modal.showModal();
      }
    });
  });

  // Close modal when close button is clicked
  if (closeButton) {
    closeButton.addEventListener('click', () => {
      modal.close();
    });
  }

  // Close modal when backdrop is clicked
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.close();
    }
  });

  // Close modal on Escape key
  modal.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      modal.close();
    }
  });

  // Re-initialize when HTMX updates the images (after upload/delete)
  document.addEventListener('htmx:afterSettle', () => {
    initializeFixtureImageModal();
  });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeFixtureImageModal);

// Also initialize if images are loaded dynamically
document.addEventListener('htmx:afterSwap', initializeFixtureImageModal);
